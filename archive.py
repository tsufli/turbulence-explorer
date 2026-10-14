"""Preserve immutable experiment data on the archive branch and refresh its UI."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import urllib.request
import urllib.parse
import zipfile


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if urllib.parse.urlparse(newurl).netloc != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


def api(path):
    request = urllib.request.Request(
        f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/{path}',
        headers={'Authorization': f'Bearer {os.environ["GH_TOKEN"]}',
                 'Accept': 'application/vnd.github+json', 'User-Agent': 'turbulence-archive'})
    return urllib.request.build_opener(SafeRedirect()).open(request, timeout=120)


def extract_results(payload, destination):
    """Copy only validated data paths, never executable assets from an old run."""
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        if 'artifact.tar' in z.namelist():
            with tarfile.open(fileobj=io.BytesIO(z.read('artifact.tar'))) as t:
                entries = {m.name.removeprefix('./'): t.extractfile(m).read()
                           for m in t.getmembers() if m.isfile()}
        else:
            entries = {n.removeprefix('./'): z.read(n) for n in z.namelist() if not n.endswith('/')}
    data = json.loads(entries['results.json'])
    if data['schema_version'] != 2 or not data['frames']:
        raise ValueError('Unsupported or empty experiment')
    files = {'results.json': entries['results.json']}
    for frame in data['frames']:
        name = frame['url']
        if not re.fullmatch(r'frames/frame-\d+\.bin', name):
            raise ValueError(f'Unexpected frame path: {name}')
        content = entries[name]
        if len(content) != frame['n'] ** 2 * 12:
            raise ValueError(f'Incomplete frame: {name}')
        files[name] = content
    # Validate the complete artifact before writing anything to the archive.
    destination.mkdir(parents=True)
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (destination / 'config.json').write_text(json.dumps(data['config'], indent=2) + '\n')
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output
    run_id = os.environ.get('ARCHIVE_RUN_ID', '')
    artifacts = []
    page = 1
    while True:
        batch = json.load(api(f'actions/artifacts?per_page=100&page={page}'))['artifacts']
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    candidates = {}
    for artifact in artifacts:
        workflow_id = str(artifact['workflow_run']['id'])
        match = re.fullmatch(r'experiment-result(?:-scan-([1-9][0-9]*))?', artifact['name'])
        if (not match and artifact['name'] != 'github-pages') or artifact['expired']:
            continue
        if run_id and workflow_id != run_id:
            continue
        rid = workflow_id + (f'-scan-{match[1]}' if match and match[1] else '')
        if (out / 'runs' / rid / 'results.json').exists():
            continue
        if rid not in candidates or match:
            candidates[rid] = artifact
    for rid, artifact in candidates.items():
        workflow_id = str(artifact['workflow_run']['id'])
        run = json.load(api(f'actions/runs/{workflow_id}'))
        # A called publisher imports outputs while its parent run is in progress.
        if workflow_id != run_id and run['conclusion'] != 'success':
            continue
        payload = api(f'actions/artifacts/{artifact["id"]}/zip').read()
        try:
            data = extract_results(payload, out / 'runs' / rid)
        except KeyError:
            # New archive Pages artifacts contain many runs, not one results.json.
            if artifact['name'] == 'github-pages':
                continue
            raise
        metadata = dict(id=rid, generated_at=data['generated_at'], config=data['config'],
                        run_url=run['html_url'], source_sha=run['head_sha'])
        if data.get('experiment_name'):
            metadata['name'] = data['experiment_name']
        (out / 'runs' / rid / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(f'Preserved experiment {rid}')
    if run_id and not any((out / 'runs').glob(f'{run_id}*/results.json')):
        raise RuntimeError('The new experiment outputs could not be archived')
    runs = [json.loads(path.read_text()) for path in (out / 'runs').glob('*/metadata.json')]
    runs.sort(key=lambda r: (r['generated_at'], r['id']), reverse=True)
    if not runs:
        raise RuntimeError('No saved experiment or recoverable output found; site left unchanged')
    (out / 'archive.json').write_text(json.dumps(dict(runs=runs), indent=2) + '\n')
    for source in Path('web').iterdir():
        shutil.copy2(source, out / source.name)
    index = (out / 'index.html').read_text()
    for name in ('style.css', 'app.js'):
        version = hashlib.sha256((out / name).read_bytes()).hexdigest()[:12]
        index = index.replace(f'"{name}"', f'"{name}?v={version}"')
    (out / 'index.html').write_text(index)
    (out / '.nojekyll').touch()
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f'## Saved experiments\n\n{len(runs)} experiments preserved in `experiment-archive`.\n\n')
        for run in runs:
            c = run['config']
            summary.write(f'- [{run["id"]}]({run["run_url"]}): {c["n"]}², α={c["alpha"]}, T={c["duration"]}\n')


if __name__ == '__main__':
    main()
