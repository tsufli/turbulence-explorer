import unittest
import numpy as np
from simulation import Config, Solver, run


class SpatialDragChecks(unittest.TestCase):
    def solver(self, **kwargs):
        return Solver(Config(n=64, kf=8, alpha=.003, alpha_right=.03, **kwargs))

    def test_constant_profile_reduces_to_uniform_friction(self):
        s = Solver(Config(n=64, kf=8, alpha=.03, alpha_right=.03))
        s.w = s.fft(s.rng.normal(size=(64, 64))) * s.mask
        s.mean_velocity[:] = [.7, -.2]
        dw, dm, dissipation = s.drag_rhs(s.w)
        np.testing.assert_allclose(dw, -.03*s.w, atol=1e-15)
        np.testing.assert_allclose(dm, -.03*s.mean_velocity, atol=1e-15)
        np.testing.assert_allclose(dissipation, 2*.03*s.totals(s.w), atol=1e-15)

    def test_full_curl_generates_interface_vorticity_from_mean_flow(self):
        s = self.solver()
        s.mean_velocity[:] = [0, 1]
        dw, dm, loss = s.drag_rhs(s.w)
        np.testing.assert_allclose(dm, [0, -(.003+.03)/2], atol=1e-15)
        for m in range(1, 21):
            expected = -(.003-.03)*(1-(-1)**m)/(2*np.pi)
            self.assertAlmostEqual(dw[0, m].real, expected, places=14)
            self.assertAlmostEqual(dw[0, m].imag, 0, places=14)
        self.assertEqual(dw[0, 0], 0)
        self.assertAlmostEqual(loss[0], (.003+.03)/2)
        self.assertAlmostEqual(loss[1], 0)

    def test_drag_energy_loss_matches_physical_power(self):
        s = self.solver()
        s.w = s.fft(s.rng.normal(size=(64, 64))) * s.mask
        s.mean_velocity[:] = [.4, -.3]
        dw, dm, loss = s.drag_rhs(s.w)
        size = 8*s.c.n
        rows = (np.fft.fftfreq(s.c.n)*s.c.n).astype(int) % size
        uhat = np.zeros((size, size//2+1), complex)
        vhat = uhat.copy()
        uhat[rows, :s.c.n//2+1] = 1j*s.ky*s.inv*s.w
        vhat[rows, :s.c.n//2+1] = -1j*s.kx*s.inv*s.w
        uhat[0, 0], vhat[0, 0] = s.mean_velocity
        u = np.fft.irfft2(uhat, s=(size,size), norm='forward')
        v = np.fft.irfft2(vhat, s=(size,size), norm='forward')
        alpha = np.where(np.arange(size)<size//2,.003,.03)
        alpha[[0,size//2]] = (.003+.03)/2
        # Independent trapezoidal integration over the two smooth halves.
        physical_power = np.mean(alpha[None,:]*(u*u+v*v))
        np.testing.assert_allclose(loss[0], physical_power, rtol=2e-4)
        self.assertGreater(loss[0], 0)
        self.assertTrue(np.all(dw[~s.mask] == 0))

    def test_mean_energy_is_included_in_spectrum_and_transfer(self):
        s = self.solver(nu=0, epsilon=0)
        s.w = s.fft(s.rng.normal(size=(64,64))) * s.mask
        s.mean_velocity[:] = [.3, .5]
        d = s.diagnostics()
        self.assertAlmostEqual(sum(d['spectrum'])*s.dk, d['energy'])
        self.assertLess(abs(d['transfer_energy_sum']), 1e-13)
        self.assertLess(abs(d['transfer_enstrophy_sum']), 1e-13)

    def test_reproducible_spatial_run_and_budget(self):
        c = Config(n=64, kf=8, alpha=.003, alpha_right=.03, duration=.2,
                   average_after=.1, sample_interval=.05, frame_interval=.1)
        a, b = run(c), run(c)
        self.assertEqual(a['samples'], b['samples'])
        self.assertLess(abs(a['summary']['energy_budget_residual']), 1e-8)
        self.assertLess(abs(a['summary']['enstrophy_budget_residual']), 1e-6)

    def test_time_step_convergence_for_heterogeneous_drag(self):
        def evolve(h):
            s = self.solver(nu=0, epsilon=0)
            s.w = s.fft(s.rng.normal(size=(64,64))) * s.mask
            s.mean_velocity[:] = [.2, -.1]
            for _ in range(round(.04/h)):
                s.step(h)
            return np.concatenate([s.w.ravel(), s.mean_velocity])
        a, b, reference = evolve(.01), evolve(.005), evolve(.00125)
        self.assertLess(np.linalg.norm(b-reference), np.linalg.norm(a-reference)/8)


if __name__ == '__main__':
    unittest.main()
