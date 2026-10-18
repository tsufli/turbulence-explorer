import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from archive import extract_results
from simulation import Config, Solver, snapshot, run


class RectangleChecks(unittest.TestCase):
    def solver(self, **kwargs):
        params = dict(n=64, nx=96, ny=32, length=6*np.pi, length_y=2*np.pi, kf=8)
        params.update(kwargs)
        return Solver(Config(**params))

    def test_rectangular_parseval_and_invariants(self):
        s = self.solver(nu=0, alpha=0, epsilon=0)
        s.w = s.fft(s.rng.normal(size=(32,96))) * s.mask
        u, v = s.velocity(s.w)
        initial = s.totals(s.w)
        np.testing.assert_allclose(initial, [np.mean(u*u+v*v)/2, np.mean(s.real(s.w)**2)/2], rtol=1e-14)
        d = s.diagnostics()
        self.assertLess(abs(d['transfer_energy_sum']), 1e-13)
        self.assertLess(abs(d['transfer_enstrophy_sum']), 1e-13)
        self.assertAlmostEqual(sum(d['spectrum'])*s.dk, d['energy'])
        for _ in range(20):
            s.step(.001)
        np.testing.assert_allclose(s.totals(s.w), initial, rtol=1e-8)

    def test_physical_wavenumbers_and_exact_decay(self):
        s = self.solver(epsilon=0)
        x = np.arange(s.nx)*s.lx/s.nx
        y = np.arange(s.ny)*s.ly/s.ny
        kx, ky = 2*2*np.pi/s.lx, 3*2*np.pi/s.ly
        s.w = s.fft(np.cos(kx*x[None,:]+ky*y[:,None])) * s.mask
        old = s.w.copy()
        s.step(.01)
        np.testing.assert_allclose(s.w, old*np.exp(-(s.c.nu*(kx*kx+ky*ky)+s.c.alpha)*.01), atol=1e-13)
        self.assertAlmostEqual(s.kx[3,2], kx)
        self.assertAlmostEqual(s.ky[3,2], ky)

    def test_rectangular_forcing_injection_normalization(self):
        s = self.solver(nu=0, alpha=0)
        totals=[]
        for _ in range(1500):
            s.w[:]=0
            s.linear_noise(.02)
            totals.append(s.totals(s.w))
        np.testing.assert_allclose(np.mean(totals,axis=0)/.02, [s.c.epsilon,s.eta], rtol=.03)

    def test_rectangular_cfl_uses_both_spacings(self):
        s = self.solver(nu=0, alpha=0, epsilon=0, length=12*np.pi, kf=4)
        s.mean_velocity[:] = [2,3]
        rate=2*s.nx/s.lx+3*s.ny/s.ly
        s.step(.1)
        self.assertAlmostEqual(s.elapsed, .25/rate)
        self.assertAlmostEqual(s.max_cfl, .25)

    def test_square_path_is_unchanged(self):
        a = Solver(Config(n=64,kf=8))
        b = Solver(Config(n=64,kf=8,nx=64,ny=64,length_y=2*np.pi))
        for _ in range(10):
            a.step(.001);b.step(.001)
        np.testing.assert_array_equal(a.w,b.w)
        np.testing.assert_array_equal(a.ledger,b.ledger)

    def test_full_rectangle_frame_and_archive_roundtrip(self):
        c=Config(**json.loads(Path('rectangle-config.json').read_text()))
        s=Solver(c)
        x=np.arange(s.nx)*s.lx/s.nx
        s.w=s.fft(np.broadcast_to(np.cos(2*np.pi*x/s.lx),(s.ny,s.nx))) * s.mask
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);frame=snapshot(s,root/'frames')
            planes=np.fromfile(root/'frames/frame-0000.bin',dtype='<f4').reshape(3,s.ny,s.nx)
            np.testing.assert_allclose(planes[0],s.real(s.w),atol=3e-8)
            payload=io.BytesIO()
            with zipfile.ZipFile(payload,'w') as z:
                z.writestr('results.json',json.dumps(dict(schema_version=2,config={},frames=[frame])))
                z.write(root/'frames/frame-0000.bin','frames/frame-0000.bin')
            extract_results(payload.getvalue(),root/'archive')
            self.assertEqual((root/'archive/frames/frame-0000.bin').stat().st_size,3*480*32*4)
        self.assertEqual((frame['nx'],frame['ny']),(480,32))
        self.assertAlmostEqual(s.lx/s.ly,15)
        self.assertAlmostEqual(s.lx*s.ly,(2*np.pi)**2)

    def test_short_rectangle_budget(self):
        c=Config(n=64,nx=96,ny=32,length=6*np.pi,length_y=2*np.pi,kf=8,
                 duration=.2,average_after=.1,sample_interval=.05,frame_interval=.1)
        data=run(c)
        self.assertLess(abs(data['summary']['energy_budget_residual']),1e-8)
        self.assertLess(abs(data['summary']['enstrophy_budget_residual']),1e-6)
        self.assertTrue(data['complete_shell_max']<32/3)

    def test_exact_strict_cutoff_for_non_power_of_two_grid(self):
        c=Config(**json.loads(Path('rectangle-config.json').read_text()))
        s=Solver(c)
        self.assertFalse(s.mask[0,160])
        self.assertTrue(s.mask[0,159])
        self.assertFalse(s.mask[11,1])
        self.assertTrue(s.mask[10,1])

    def test_forcing_must_fit_short_direction(self):
        with self.assertRaises(ValueError):
            self.solver(ny=16)


if __name__ == '__main__':
    unittest.main()
