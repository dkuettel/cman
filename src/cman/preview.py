import os
from pathlib import Path
from subprocess import CalledProcessError, run

from flask import Flask, current_app, redirect, url_for

template_path = Path(__file__).parent / "preview-template.html"
template_path = template_path.absolute()

app = Flask(__name__)


@app.route("/")
def index():
    return redirect(url_for("preview"))


@app.route("/preview")
def preview():
    # NOTE we read the time _before_ we use it, so worst case it's old, but never new
    path = get_most_recent_md(current_app.config["watch_folder"])
    if path is None:
        return "n/a"
    stat = path.stat()
    name = path.relative_to(current_app.config["watch_folder"])
    try:
        result = run(
            [
                "pandoc",
                str(path),
                # needs to be local, because --self-contained copies it everytime
                # (using https://cdn.jsdelivr.net/npm/katex@0.16.4/dist/ will rate-limit)
                f"--katex={os.environ['h']}/result/lib/node_modules/katex/dist/",
                f"--metadata=pagetitle={name}",
                # to find images relative to the markdown file
                f"--resource-path={path.parent}",
                # embeds images, and even katex
                # plus output is a full html document
                # (otherwise it's a html sub-tree)
                "--self-contained",
                # adapted from 'pandoc -D html'
                f"--template={template_path}",
                f"--variable=preview_name:{name}",
                f"--variable=mtime:{stat.st_mtime}",
                "--to=html",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        return result.stdout
    except CalledProcessError as e:
        return e.stdout + e.stderr


@app.route("/mtime")
def mtime():
    path = get_most_recent_md(current_app.config["watch_folder"])
    if path is None:
        return {"mtime": -1}
    stat = path.stat()
    return {"mtime": stat.st_mtime}


def get_most_recent_md(folder: Path) -> None | Path:
    candidates = folder.glob("**/*.md")
    candidates = sorted(candidates, key=lambda c: c.stat().st_mtime)
    if len(candidates) == 0:
        return None
    return candidates[-1]


def main(watch_folder: Path = Path("./data")):
    app.config["watch_folder"] = watch_folder
    app.run()
