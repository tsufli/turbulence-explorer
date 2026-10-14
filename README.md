# 2D Turbulence Explorer

A reproducible Python simulation of incompressible 2D Navier–Stokes, with an interactive GitHub Pages dashboard showing **computed** full-resolution vorticity, energy spectra, energy flux and enstrophy flux.

Vorticity uses every point of the simulation grid without downsampling or scale filtering. Spatial frames load on demand and a small cache keeps playback memory bounded.

## Start on GitHub

1. Create a **public** repository called `turbulence-explorer` and upload these files, including `.github/workflows/simulate.yml`. Use `main` as the default branch.
2. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
3. Open **Actions → Simulate and publish → Run workflow**. Changes to simulation/configuration files on `main` also start a run; dashboard edits only republish the archive.
4. When both jobs finish, the deployment link appears in the run and in Settings → Pages. Open that link to explore results without downloading anything.

No tokens, API keys, email credentials or paid services are needed by the workflow. The deployed site is public. It opens the latest successful experiment. Use **Saved experiment** to revisit previous results; the URL with `?run=RUN_ID` is a permanent link. Results and full-resolution frames are committed to the separate `experiment-archive` branch, never to the source branch. Failed simulations leave saved experiments intact. There is no live streaming during the run.

## Experiment archive

Each successful run saves its parameters, diagnostics and full-resolution frames under its unique GitHub run ID. Results remain in the `experiment-archive` branch without an artifact expiration date. The first archive publication imports any previous Pages outputs that are still available; expired outputs cannot be recovered from GitHub artifacts.

To experiment without editing the defaults, open **Actions → Simulate and publish → Run workflow**, choose `standard`, and enter JSON overrides, for example `{"alpha":0.01,"alpha_right":null,"duration":200,"average_after":100}`. Each run starts from zero and adds a new entry. The original experiments remain selectable. The **New experiment** link on the dashboard opens this workflow.

**Publish experiment archive** can also be run manually to refresh the dashboard or import available outputs without running the solver.

## Change parameters

Edit `config.json` and commit, or choose a workflow preset with optional JSON overrides. Example:

```json
{"nu":0.001,"alpha":0.02,"alpha_right":null,"epsilon":0.1,"seed":7,"duration":150,"average_after":75}
```

| Parameter | Default | Meaning |
|---|---:|---|
| `n` | 128 | Square grid; choices 64, 128, 256, 512 |
| `length` | 2π | Side of periodic square box; kmin = 2π/L |
| `nu` | 0.0005 | Ordinary viscosity, no hyperviscosity |
| `alpha` | 0.003 | Uniform drag, or left-half drag when `alpha_right` is set |
| `alpha_right` | 0.03 | Right-half drag; `null` selects uniform drag |
| `epsilon` | 0.1 | Expected kinetic energy injection per unit time |
| `kf` | 16 | Forcing ring center in physical wavenumber |
| `bandwidth` | 2 | Full radial width of forcing ring |
| `dt` | 0.01 | Maximum timestep; advective CFL target 0.25 |
| `duration` | 800 | End time |
| `average_after` | 400 | Start of trapezoidal time averages |
| `sample_interval` | 1 | Spectrum/flux/history sampling |
| `frame_interval` | 10 | Vorticity snapshot sampling |
| `seed` | 42 | Reproducible Gaussian random generator |

`quick`: 64², kf=8, T=30, averaging after 15. `standard`: values in `config.json`. `extended`: 256², kf=32, ν=0.00015, T=200, averaging after 100. Overrides apply after presets. Changing box size changes physical mode spacing; keep the forcing band inside the dealiased disk. The code validates this.

There is no forcing correlation time parameter: this implementation is **white in time**, with Gaussian amplitudes and a top-hat radial covariance in Fourier space, not a Gaussian spatial covariance. Initial velocity is zero. Mean vorticity remains zero; spatial drag can generate mean velocity. All quantities use the nondimensional units chosen by these parameters.

## Drag scan 1–7

The **Drag scan** workflow runs seven independent, uniform-drag experiments at 128², T=300, averaging 150–300. Drag decreases logarithmically from 0.03 to 0.003. All runs start from zero with seed 42 and otherwise use the same physical parameters. Explicit `alpha_right: null` disables spatial drag. Runs are named `drag scan 1` through `drag scan 7`, and each is preserved separately in the archive. Three simulations run concurrently; all completed outputs are published after the batch finishes. This short scan compares transient vortex formation, not stationary transition thresholds.

The scan definition is in `drag-scan.json`. Run **Actions → Drag scan → Run workflow** to repeat it.

## Spatial drag experiment

Set `alpha_right` to enable left/right half-box friction: `alpha` applies for 0 ≤ x < L/2 and `alpha_right` for L/2 ≤ x < L. Omit it or set it to `null` for uniform drag. Current experiment: 128², left 0.003, right 0.03, T=800, averaging 400–800; all other physical parameters are unchanged.

This is a velocity force −α(x)u, so its full curl is used, including interface effects. Spatial friction can generate a box-mean velocity, which is evolved and included in total energy and the k=0 spectral shell. The drag step has exact Fourier coefficients; padded products give its Galerkin projection without aliasing. Spatial drag is integrated alongside advection with RK4, between viscosity/forcing OU half-steps. The original uniform-drag integration path is retained. Energy flux measures nonlinear transfer only, excluding the drag contribution. Drag removes kinetic energy; its contribution to enstrophy need not be positive near the interfaces.

To return to uniform drag using workflow overrides, include `"alpha_right":null`.

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

Open `http://localhost:8000`. All graphs are drawn with browser Canvas; no external CDN is required. Physics tests verify Parseval normalization, Biot–Savart sign, conservation, viscous decay, forcing covariance, flux cutoff/sign and full-grid frame export.

`results.json` schema version 2 contains frame times and URLs. Each `frames/frame-NNNN.bin` contains three row-major little-endian float32 N×N planes, ordered ω, ux, uy. Float32 is used only to transfer visualization fields; the solver and spectral diagnostics still use float64, with unchanged equations, parameters, random forcing and timestepping. The global vorticity color limit is recorded from the full grid across the run. Frames are published alongside the dashboard, without adding numerical data to the source branch.

References: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [2D Gaussian white-noise stirring and cascade regimes](https://arxiv.org/abs/0907.3396).
