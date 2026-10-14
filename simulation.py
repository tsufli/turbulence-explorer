"""Dealiased 2D Navier–Stokes with additive Gaussian white-in-time forcing.

All FFTs use norm='forward': spatial mean energy = sum of modal energies.
The domain is periodic, with zero mean vorticity. Spatial drag can generate mean velocity.
"""
from dataclasses import dataclass, asdict
import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import numpy as np
from scipy.fft import rfft2, irfft2


@dataclass
class Config:
    n: int = 128
    length: float = 2 * np.pi
    nu: float = 0.0005
    alpha: float = 0.03
    alpha_right: float | None = None  # None: uniform; otherwise left/right halves
    epsilon: float = 0.1
    kf: float = 16.0
    bandwidth: float = 2.0
    dt: float = 0.01
    duration: float = 120.0
    average_after: float = 60.0
    sample_interval: float = 0.5
    frame_interval: float = 1.0
    seed: int = 42


class Solver:
    def __init__(self, c):
        self.c = c
        if c.n not in (64, 128, 256, 512):
            raise ValueError('n must be 64, 128, 256 or 512')
        vals = np.array([c.length, c.nu, c.alpha, c.epsilon, c.kf, c.bandwidth,
                         c.dt, c.duration, c.average_after, c.sample_interval, c.frame_interval])
        if not np.isfinite(vals).all():
            raise ValueError('All parameters must be finite')
        if min(c.length, c.kf, c.bandwidth, c.dt, c.duration, c.sample_interval, c.frame_interval) <= 0:
            raise ValueError('Lengths, time intervals and forcing scales must be positive')
        if min(c.nu, c.alpha, c.epsilon, c.average_after) < 0 or c.average_after >= c.duration:
            raise ValueError('Use nonnegative dissipation/forcing and 0 <= average_after < duration')
        if c.alpha_right is not None and (not np.isfinite(c.alpha_right) or c.alpha_right < 0):
            raise ValueError('Right-half drag must be finite and nonnegative')
        self.spatial_drag = c.alpha_right is not None
        self.mean_velocity = np.zeros(2)
        self.dk = 2 * np.pi / c.length
        qx = np.fft.rfftfreq(c.n) * c.n
        qy = np.fft.fftfreq(c.n) * c.n
        self.kx, self.ky = np.meshgrid(qx * self.dk, qy * self.dk)
        self.k2 = self.kx**2 + self.ky**2
        self.inv = np.divide(1., self.k2, out=np.zeros_like(self.k2), where=self.k2 > 0)
        # Strict inequality removes alias-producing boundary triads.
        self.mask = (abs(qy[:, None]) < c.n / 3) & (qx[None, :] < c.n / 3)
        self.mask[0, 0] = False
        self.weights = np.broadcast_to(np.where((qx == 0) | (qx == c.n / 2), 1., 2.), self.k2.shape)
        self.radius = np.sqrt(self.k2)
        self.band = self.mask & (abs(self.radius - c.kf) <= c.bandwidth / 2)
        if not self.band.any() or c.kf + c.bandwidth / 2 >= (c.n / 3) * self.dk:
            raise ValueError('Forcing band must fit inside the complete dealiased disk')
        self.shell = np.floor(self.radius / self.dk + 0.5).astype(int)
        self.nshell = self.shell.max() + 1
        self.decay_rate = c.nu * self.k2 + (0 if self.spatial_drag else c.alpha)
        if self.spatial_drag:
            # Exact Fourier coefficients of the periodic left/right step.
            # Only |m| <= 2*cut can couple two retained velocity modes.
            # Products on a doubled grid therefore recover the Galerkin
            # projection without sampling/aliasing the discontinuity.
            self.drag_n = 2 * c.n
            self.drag_rows = (np.fft.fftfreq(c.n) * c.n).astype(int) % self.drag_n
            cut = int(np.ceil(c.n / 3)) - 1
            alpha_hat = np.zeros((self.drag_n, self.drag_n // 2 + 1), complex)
            alpha_hat[0, 0] = (c.alpha + c.alpha_right) / 2
            m = np.arange(1, 2 * cut + 1)
            alpha_hat[0, m] = (c.alpha - c.alpha_right) * (1 - (-1.)**m) / (2j * np.pi * m)
            self.drag_profile = irfft2(alpha_hat, s=(self.drag_n, self.drag_n), norm='forward')
        # A real-space unit Gaussian FFT has E|q_hat|² = 1/n².
        # Choose covariance, rather than normalizing individual realizations.
        s = np.sum(self.weights * self.band * self.inv)
        self.sigma = np.sqrt(2 * c.epsilon * c.n**2 / s)
        self.eta = c.epsilon * np.sum(self.weights * self.band) / s
        self.rng = np.random.default_rng(c.seed)
        self.w = np.zeros_like(self.k2, dtype=complex)
        self.elapsed = 0.
        self.ledger = np.zeros(4)  # noise E, damping E, noise Z, damping Z
        self.max_cfl = 0.

    def fft(self, a):
        return rfft2(a, norm='forward')

    def real(self, a):
        return irfft2(a, s=(self.c.n, self.c.n), norm='forward')

    def velocity(self, w, mean=None):
        # omega = dx(v)-dy(u); u_hat=i ky omega_hat/k², v_hat=-i kx omega_hat/k².
        if mean is None:
            mean = self.mean_velocity
        return self.real(1j * self.ky * self.inv * w) + mean[0], self.real(-1j * self.kx * self.inv * w) + mean[1]

    def nonlinear(self, w, mean=None):
        u, v = self.velocity(w, mean)
        return -self.fft(u * self.real(1j * self.kx * w) + v * self.real(1j * self.ky * w)) * self.mask

    def totals(self, w, mean=None):
        a = self.weights * abs(w)**2 * 0.5
        if mean is None:
            mean = self.mean_velocity
        return np.array([np.sum(a * self.inv) + 0.5 * np.dot(mean, mean), np.sum(a)])

    def drag_rhs(self, w, mean=None):
        """curl(-alpha(x) velocity), projected onto retained incompressible modes."""
        if mean is None:
            mean = self.mean_velocity
        shape = (self.drag_n, self.drag_n // 2 + 1)
        uh, vh = np.zeros(shape, complex), np.zeros(shape, complex)
        uh[self.drag_rows, :self.c.n // 2 + 1] = 1j * self.ky * self.inv * w
        vh[self.drag_rows, :self.c.n // 2 + 1] = -1j * self.kx * self.inv * w
        uh[0, 0], vh[0, 0] = mean
        u = irfft2(uh, s=(self.drag_n, self.drag_n), norm='forward')
        v = irfft2(vh, s=(self.drag_n, self.drag_n), norm='forward')
        fu = rfft2(-self.drag_profile * u, norm='forward')
        fv = rfft2(-self.drag_profile * v, norm='forward')
        dw = (1j * self.kx * fv[self.drag_rows, :self.c.n // 2 + 1]
              - 1j * self.ky * fu[self.drag_rows, :self.c.n // 2 + 1]) * self.mask
        dm = np.array([fu[0, 0].real, fv[0, 0].real])
        rate_z = self.weights * np.real(np.conj(w) * dw)
        dissipation = np.array([-np.sum(rate_z * self.inv) - np.dot(mean, dm), -np.sum(rate_z)])
        return dw, dm, dissipation

    def spatial_rhs(self, w, mean):
        dw, dm, dissipation = self.drag_rhs(w, mean)
        return self.nonlinear(w, mean) + dw, dm, dissipation

    def linear_noise(self, h):
        before = self.totals(self.w)
        self.w *= np.exp(-self.decay_rate * h)
        damped = self.totals(self.w)
        if self.c.epsilon:
            variance_time = np.divide(-np.expm1(-2 * self.decay_rate * h), 2 * self.decay_rate,
                                      out=np.full_like(self.k2, h), where=self.decay_rate > 0)
            q = self.fft(self.rng.standard_normal((self.c.n, self.c.n)))
            self.w += self.sigma * np.sqrt(variance_time) * self.band * q
        noise = self.totals(self.w) - damped
        damping = before - damped
        self.ledger += [noise[0], damping[0], noise[1], damping[1]]

    def step(self, h):
        # Symmetric splitting: exact stochastic OU half-step / RK4 / OU.
        u, v = self.velocity(self.w)
        advective_rate = self.c.n / self.c.length * np.max(abs(u) + abs(v))
        if advective_rate > 0:
            h = min(h, 0.25 / advective_rate)
        cfl = h * advective_rate
        self.max_cfl = max(self.max_cfl, float(cfl))
        if cfl > 0.65:
            raise RuntimeError(f'CFL={cfl:.3f} exceeds 0.65; reduce dt')
        self.linear_noise(h / 2)
        w0 = self.w.copy()
        if self.spatial_drag:
            m0 = self.mean_velocity.copy()
            k1, m1, d1 = self.spatial_rhs(w0, m0)
            k2, m2, d2 = self.spatial_rhs(w0 + h*k1/2, m0 + h*m1/2)
            k3, m3, d3 = self.spatial_rhs(w0 + h*k2/2, m0 + h*m2/2)
            k4, m4, d4 = self.spatial_rhs(w0 + h*k3, m0 + h*m3)
            self.mean_velocity = m0 + h*(m1 + 2*m2 + 2*m3 + m4)/6
            dissipated = h*(d1 + 2*d2 + 2*d3 + d4)/6
            self.ledger += [0, dissipated[0], 0, dissipated[1]]
        else:
            k1 = self.nonlinear(w0)
            k2 = self.nonlinear(w0 + h * k1 / 2)
            k3 = self.nonlinear(w0 + h * k2 / 2)
            k4 = self.nonlinear(w0 + h * k3)
        self.w = (w0 + h * (k1 + 2*k2 + 2*k3 + k4) / 6) * self.mask
        self.linear_noise(h / 2)
        if not np.isfinite(self.w).all():
            raise RuntimeError('Nonfinite vorticity; reduce dt')
        self.elapsed += h

    def shells(self, a):
        return np.bincount(self.shell.ravel(), weights=a.ravel(), minlength=self.nshell)

    def diagnostics(self):
        a = 0.5 * self.weights * abs(self.w)**2
        transfer_z = self.weights * np.real(np.conj(self.w) * self.nonlinear(self.w))
        transfer_e = transfer_z * self.inv
        e, z = self.totals(self.w)
        spectrum = self.shells(a * self.inv) / self.dk
        spectrum[0] += 0.5 * np.dot(self.mean_velocity, self.mean_velocity) / self.dk
        drag_dissipation = self.drag_rhs(self.w)[2] if self.spatial_drag else np.zeros(2)
        return dict(t=float(self.elapsed), energy=float(e), enstrophy=float(z),
                    spectrum=spectrum.tolist(),
                    mean_velocity=self.mean_velocity.tolist(),
                    enstrophy_spectrum=(self.shells(a) / self.dk).tolist(),
                    energy_flux=(-np.cumsum(self.shells(transfer_e))).tolist(),
                    enstrophy_flux=(-np.cumsum(self.shells(transfer_z))).tolist(),
                    energy_dissipation=float(np.sum(2 * self.decay_rate * a * self.inv) + drag_dissipation[0]),
                    enstrophy_dissipation=float(np.sum(2 * self.decay_rate * a) + drag_dissipation[1]),
                    transfer_energy_sum=float(transfer_e.sum()),
                    transfer_enstrophy_sum=float(transfer_z.sum()),
                    noise_energy=float(self.ledger[0]), damping_energy=float(self.ledger[1]),
                    noise_enstrophy=float(self.ledger[2]), damping_enstrophy=float(self.ledger[3]))


def snapshot(solver, directory=None, index=0):
    """Export the unfiltered full grid; this never mutates solver state or RNG."""
    omega = solver.real(solver.w)
    u, v = solver.velocity(solver.w)
    frame = dict(t=float(solver.elapsed), n=solver.c.n,
                 vorticity_max=float(np.max(abs(omega))),
                 speed_max=float(np.max(np.hypot(u, v))))
    if directory is None:
        frame.update(values=omega.tolist(), u=u.tolist(), v=v.tolist())
    else:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        name = f'frame-{index:04d}.bin'
        # Three row-major little-endian float32 planes: omega, ux, uy.
        # Only display data use float32; solver state/diagnostics remain float64.
        np.stack((omega, u, v)).astype('<f4').tofile(directory / name)
        frame['url'] = 'frames/' + name
    return frame


def run(c, frame_directory=None):
    solver = Solver(c)
    start = time.monotonic()
    samples, frames = [], []
    next_sample = next_frame = 0.
    next_report = 10.
    while True:
        if (solver.elapsed + 1e-9 >= next_sample or solver.elapsed + 1e-9 >= c.duration
                or abs(solver.elapsed - c.average_after) < 1e-9):
            samples.append(solver.diagnostics())
            if solver.elapsed + 1e-9 >= next_sample:
                next_sample += c.sample_interval
        if solver.elapsed + 1e-9 >= next_frame or solver.elapsed + 1e-9 >= c.duration:
            frames.append(snapshot(solver, frame_directory, len(frames)))
            next_frame += c.frame_interval
        if solver.elapsed + 1e-9 >= c.duration:
            break
        # Align steps to sample/frame boundaries and averaging start.
        targets = [c.dt, c.duration - solver.elapsed, next_sample - solver.elapsed, next_frame - solver.elapsed]
        if solver.elapsed < c.average_after - 1e-9:
            targets.append(c.average_after - solver.elapsed)
        solver.step(min(x for x in targets if x > 1e-9))
        if solver.elapsed >= next_report:
            print(f't={solver.elapsed:.1f}/{c.duration:g}; wall={time.monotonic()-start:.1f}s', flush=True)
            next_report += 10
    # Piecewise linear trapezoidal averages over saved diagnostics; include t0.
    selected = [s for s in samples if s['t'] >= c.average_after - 1e-9]
    if len(selected) < 2:
        raise ValueError('Averaging window needs at least two diagnostic samples')
    times = np.array([s['t'] for s in selected])
    keys = ['spectrum', 'enstrophy_spectrum', 'energy_flux', 'enstrophy_flux',
            'energy', 'enstrophy', 'energy_dissipation', 'enstrophy_dissipation']
    avg = {key: np.trapezoid(np.array([s[key] for s in selected]), times, axis=0) / (times[-1] - times[0]) for key in keys}
    avg = {key: np.asarray(val).tolist() for key, val in avg.items()}
    last = samples[-1]
    residual_e = last['energy'] - last['noise_energy'] + last['damping_energy']
    residual_z = last['enstrophy'] - last['noise_enstrophy'] + last['damping_enstrophy']
    k = np.arange(solver.nshell) * solver.dk
    inverse = (k >= 3 * solver.dk) & (k < c.kf - c.bandwidth / 2 - solver.dk)
    summary = dict(wall_seconds=time.monotonic()-start, max_cfl=solver.max_cfl,
                   energy_budget_residual=residual_e, enstrophy_budget_residual=residual_z,
                   average_start=float(times[0]), average_end=float(times[-1]),
                   average_sample_count=len(selected),
                   inverse_range_mean_flux=float(np.mean(np.array(avg['energy_flux'])[inverse])) if inverse.any() else None,
                   stationarity='Not certified: assess histories and repeat with longer averaging.',
                   expected_energy_injection=c.epsilon, expected_enstrophy_injection=float(solver.eta))
    return dict(schema_version=2, generated_at=datetime.now(timezone.utc).isoformat(),
                config=asdict(c), summary=summary, k=k.tolist(),
                flux_k=(k + solver.dk / 2).tolist(), complete_shell_max=float((c.n / 3 - 1) * solver.dk),
                samples=samples, frames=frames, average=avg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--output', default='site')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    data = run(Config(**json.loads(Path(args.config).read_text())), out / 'frames')
    for src in Path(__file__).parent.joinpath('web').iterdir():
        shutil.copy2(src, out / src.name)
    # A new field schema must not run with an older cached dashboard script.
    index = (out / 'index.html').read_text()
    for name in ('style.css', 'app.js'):
        version = hashlib.sha256((out / name).read_bytes()).hexdigest()[:12]
        index = index.replace(f'"{name}"', f'"{name}?v={version}"')
    (out / 'index.html').write_text(index)
    (out / 'results.json').write_text(json.dumps(data, separators=(',', ':'), allow_nan=False))
    (out / '.nojekyll').touch()
    print(json.dumps(data['summary'], indent=2))


if __name__ == '__main__':
    main()
