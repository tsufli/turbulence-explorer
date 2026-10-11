# 2D Turbulence Explorer

A reproducible Python simulation of incompressible 2D Navier–Stokes, with an interactive GitHub Pages dashboard showing **computed** vorticity, energy spectra, energy flux and enstrophy flux.

## Start on GitHub

1. Create a **public** repository called `turbulence-explorer` and upload these files, including `.github/workflows/simulate.yml`. Use `main` as the default branch.
2. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
3. Open **Actions → Simulate and publish → Run workflow**. The first push to `main` also starts a standard run.
4. When both jobs finish, the deployment link appears in the run and in Settings → Pages. Open that link to explore results without downloading anything.

No tokens, API keys, email credentials or paid services are needed by the workflow. The deployed site is public. It displays the latest successful run; failed runs leave the prior site intact. Results are generated inside Actions and deployed as a Pages artifact, never committed to the source branch. There is no live streaming during the run.

## Change parameters

Edit `config.json` and commit, or choose a workflow preset with optional JSON overrides. Example:

```json
{"nu":0.001,"alpha":0.02,"epsilon":0.1,"seed":7,"duration":150,"average_after":75}
```

| Parameter | Default | Meaning |
|---|---:|---|
| `n` | 128 | Square grid; choices 64, 128, 256, 512 |
| `length` | 2π | Side of periodic square box; kmin = 2π/L |
| `nu` | 0.0005 | Ordinary viscosity, no hyperviscosity |
| `alpha` | 0.03 | Linear drag on all retained modes |
| `epsilon` | 0.1 | Expected kinetic energy injection per unit time |
| `kf` | 16 | Forcing ring center in physical wavenumber |
| `bandwidth` | 2 | Full radial width of forcing ring |
| `dt` | 0.01 | Maximum timestep; advective CFL target 0.25 |
| `duration` | 120 | End time |
| `average_after` | 60 | Start of trapezoidal time averages |
| `sample_interval` | 0.5 | Spectrum/flux/history sampling |
| `frame_interval` | 1 | Vorticity snapshot sampling |
| `seed` | 42 | Reproducible Gaussian random generator |

`quick`: 64², kf=8, T=30, averaging after 15. `standard`: values in `config.json`. `extended`: 256², kf=32, ν=0.00015, T=200, averaging after 100. Overrides apply after presets. Changing box size changes physical mode spacing; keep the forcing band inside the dealiased disk. The code validates this.

There is no forcing correlation time parameter: this implementation is **white in time**, with Gaussian amplitudes and a top-hat radial covariance in Fourier space, not a Gaussian spatial covariance. Initial velocity is zero. The zero mode remains zero. All quantities use the nondimensional units chosen by these parameters.

## Numerical method

We solve ∂tω + u·∇ω = ν∇²ω − αω + fω on a periodic square. With ω=∂xuy−∂yux, Fourier velocity is (i ky ωhat/k², −i kx ωhat/k²). The nonlinear advection is evaluated pseudospectrally with strict 2/3 truncation. Real FFTs use `norm='forward'` and the appropriate multiplicity weights.

Time integration uses symmetric splitting: an exact stochastic Ornstein–Uhlenbeck linear half-step, an RK4 nonlinear step, then another independent stochastic linear half-step. The additive noise has fixed Gaussian covariance, normalized so its continuous-time expected energy injection is ε. **Individual kicks are not rescaled to fixed energy**, which would spoil Gaussian statistics. Expected enstrophy injection is also recorded. Timestep control uses the pre-step velocity; convergence should still be checked by lowering `dt`.

Each shell is centered at j Δk with edges (j±½)Δk. E(k) is shell energy divided by Δk. The nonlinear modal transfers are TE(q)=Re[ωhat* Nhat]/q² and TZ(q)=Re[ωhat* Nhat], where Nhat is Fourier −u·∇ω. Positive flux means low modes lose invariant content: Π(K)=−Σ|q|<K T(q). The dashboard uses shell-boundary cutoffs K=(j+½)Δk and only plots complete radial shells. The full stored shell sum reproduces the total energy.

Totals, dissipation rates, instantaneous sums of nonlinear transfers, advective CFL and discrete energy/enstrophy budget residuals are saved with each run. The discrete budget tracks exact linear damping followed by the propagated stochastic increment in each OU substep; its realized noise work includes cross terms and is not exactly ε times duration. Budget residuals measure the drift incurred in the nonlinear integration. Averages are trapezoidal integrals over saved diagnostic times, including the averaging start.

## Interpretation

The 128² default is an **exploratory run**, with limited scale separation. Negative time-averaged ΠE below the forcing band is evidence for inverse transfer. Positive ΠZ above it supports forward enstrophy transfer. Slope guides are illustrative reference slopes over real computed data, not fits or evidence of scaling. No stationary state or universal exponent is automatically asserted.

Before making quantitative claims, compare longer averaging windows, independent seeds, smaller timesteps and higher resolutions. Inspect histories, dissipation and the viscous tail; an underresolved forward cascade can contaminate the inverse range. Linear drag acts at every scale. A box-scale condensate can develop when drag is weak. No uncertainty bars or convergence certification are supplied by this initial version.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python simulation.py --config config.json --output site
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. All graphs are drawn with browser Canvas; no external CDN is required. Physics tests verify Parseval normalization, Biot–Savart sign, conservation, viscous decay, forcing covariance and flux cutoff/sign. The vorticity display is downsampled to at most 64²; all diagnostics use the full grid.

References: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [2D Gaussian white-noise stirring and cascade regimes](https://arxiv.org/abs/0907.3396).
