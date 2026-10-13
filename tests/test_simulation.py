import unittest
import tempfile
from pathlib import Path
import numpy as np
from simulation import Config, Solver, run, snapshot


class PhysicsChecks(unittest.TestCase):
    def solver(self, **kwargs):
        return Solver(Config(n=64, kf=8, **kwargs))

    def test_parseval_and_velocity_sign(self):
        s = self.solver()
        x = np.arange(64) * 2 * np.pi / 64
        w = np.broadcast_to(np.cos(x)[None, :], (64, 64))
        s.w = s.fft(w)
        u, v = s.velocity(s.w)
        np.testing.assert_allclose(u, 0, atol=1e-14)
        np.testing.assert_allclose(v, np.broadcast_to(np.sin(x), (64, 64)), atol=1e-13)
        e, z = s.totals(s.w)
        self.assertAlmostEqual(e, .25)
        self.assertAlmostEqual(z, .25)
        self.assertAlmostEqual(e, np.mean(u*u+v*v)/2)
        self.assertAlmostEqual(z, np.mean(w*w)/2)

    def test_inviscid_nonlinearity_conserves_both_invariants(self):
        s = self.solver(nu=0, alpha=0, epsilon=0)
        s.w = s.fft(s.rng.normal(size=(64, 64))) * s.mask
        d = s.diagnostics()
        self.assertLess(abs(d['transfer_energy_sum']), 1e-13)
        self.assertLess(abs(d['transfer_enstrophy_sum']), 1e-13)
        initial = s.totals(s.w)
        for _ in range(20):
            s.step(.001)
        np.testing.assert_allclose(s.totals(s.w), initial, rtol=1e-8)

    def test_single_mode_exact_viscous_decay(self):
        s = self.solver(epsilon=0)
        x = np.arange(64) * 2*np.pi/64
        s.w = s.fft(np.broadcast_to(np.cos(3*x), (64, 64)))
        old = s.w.copy()
        s.step(.05)
        np.testing.assert_allclose(s.w, old*np.exp(-(9*s.c.nu+s.c.alpha)*.05), atol=1e-13)

    def test_gaussian_forcing_covariance_injection(self):
        s = self.solver(nu=0, alpha=0)
        values = []
        for _ in range(1500):
            s.w[:] = 0
            s.linear_noise(.02)
            values.append(s.totals(s.w))
        mean = np.mean(values, axis=0)/.02
        np.testing.assert_allclose(mean, [s.c.epsilon, s.eta], rtol=.03)
        self.assertTrue(np.all(s.w[~s.band] == 0))

    def test_flux_sign_and_cutoff(self):
        s = self.solver()
        s.w = s.fft(s.rng.normal(size=(64, 64))) * s.mask
        d = s.diagnostics()
        nonlinear = s.nonlinear(s.w)
        cutoff = 5.5*s.dk
        rate = np.sum(s.weights*(s.radius < cutoff)*np.real(s.w.conj()*nonlinear)*s.inv)
        self.assertAlmostEqual(d['energy_flux'][5], -rate)
        self.assertAlmostEqual(sum(d['spectrum'])*s.dk, d['energy'])
        self.assertAlmostEqual(d['energy_flux'][-1], 0.)

    def test_reproducibility_and_budget(self):
        c = Config(n=64, kf=8, duration=.2, average_after=.1,
                   sample_interval=.05, frame_interval=.1)
        a, b = run(c), run(c)
        self.assertEqual(a['samples'], b['samples'])
        self.assertLess(abs(a['summary']['energy_budget_residual']), 1e-8)
        self.assertLess(abs(a['summary']['enstrophy_budget_residual']), 1e-6)

    def test_full_grid_frame_and_velocity_export(self):
        s = self.solver()
        x = np.arange(64)*2*np.pi/64
        omega = np.broadcast_to(np.cos(3*x), (64, 64))
        s.w = s.fft(omega)
        before = s.w.copy()
        rng_before = repr(s.rng.bit_generator.state)
        with tempfile.TemporaryDirectory() as directory:
            meta = snapshot(s, directory)
            planes = np.fromfile(Path(directory)/'frame-0000.bin', dtype='<f4').reshape(3, 64, 64)
        self.assertEqual(meta['n'], 64)
        np.testing.assert_allclose(planes[0], omega, atol=3e-8)
        np.testing.assert_allclose(planes[1], 0, atol=1e-14)
        np.testing.assert_allclose(planes[2], np.broadcast_to(np.sin(3*x)/3, (64, 64)), atol=3e-8)
        np.testing.assert_array_equal(before, s.w)
        self.assertEqual(rng_before, repr(s.rng.bit_generator.state))


if __name__ == '__main__':
    unittest.main()
