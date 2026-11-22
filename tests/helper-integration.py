#!/usr/bin/env python3
"""Integration checks with a local NuGet source and generated video; no network sources."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def live_timeline_lead_log_cycle():
    with tempfile.TemporaryDirectory(prefix="jkstack-live-") as tmp:
        work = Path(tmp) / "work"
        env = dict(os.environ, HOME=tmp, PYTHONDONTWRITEBYTECODE="1")
        py = lambda *a, **k: subprocess.run([sys.executable, *map(str, a)], env=env, capture_output=True, text=True, timeout=60, **k)
        live = lambda name, *a, **k: py(work / "live" / name, *a, **k)
        init = py(ROOT / "skills/live-timeline/scripts/init.py", work, "--owner", "Owner", "--lanes", "build:Build lane",
                  "--tz", "+10:00", "--empty", "--lead-log", "LEAD-LOG.md")
        assert init.returncode == 0, init.stdout + init.stderr
        log = work / "LEAD-LOG.md"
        log.write_text("# Lead log: demo (2026-11-20, UTC+10)\n\n"
                       "- 23:30 (build/opus) [chapter: Core loop - Build the loop.] [start] Opus builds the loop.\n"
                       "- 23:50 (owner) [nudge] Owner: keep it small.\n"
                       "- 00:10 (build) [result] [done: Opus builds the loop] Loop passes 40 tests. [metric: Loop tests = 40]\n")
        first = live("collect.py")
        assert "DRAFT from LEAD-LOG.md: 3 beats" in first.stdout, first.stdout + first.stderr
        assert live("collect.py").stdout.count("d3 Sat 00:10") == 1, "a pass must repeat until patch.py commits it"
        fill = {"draft": True, "fill": {"d1": {"title": "Opus builds the loop"}, "d3": {"title": "Loop passes 40 tests", "causedBy": ["@d1"]}}}
        patched = live("patch.py", input=json.dumps(fill))
        assert patched.returncode == 0, patched.stdout + patched.stderr
        assert json.loads(patched.stdout.splitlines()[-1])["committed"] is True
        assert "SOURCE" not in live("collect.py").stdout
        live("patch.py", input="{}")
        with log.open("a") as f:
            f.write("- 00:30 (build) [start] Opus starts the screens. [thread: th_1]\n")
        woke = live("collect.py", "--wait", "1m")
        assert "d1 00:30" in woke.stdout, woke.stdout
        patched = live("patch.py", input='{"draft": true}')
        assert patched.returncode == 0, patched.stdout + patched.stderr
        feed = json.loads((work / "live/events.json").read_text())
        start = feed["events"][0]
        assert (start["state"], start["end"], start["model"]) == ("done", "2026-11-21T00:10:00+10:00", "opus"), start
        assert feed["events"][-1]["thread"] == "th_1" and feed["metrics"][0]["value"] == 40
        edit = live("patch.py", input=json.dumps({"editChapters": {"c1": {"digest": "Loop built.", "keyBeats": ["e003"]}}}))
        assert edit.returncode == 0, edit.stdout + edit.stderr
        assert "digest: Loop built." in live("digest.py").stdout and "Loop built." in live("brief.py", "--since", "all").stdout
        assert live("validate.py").returncode == 0
        quiet = live("collect.py", "--wait", "1s")
        assert "QUIET for 1 s: nothing new." in quiet.stdout, quiet.stdout
        print("PASS live timeline: lead-log draft, fill, staged cursor, wait, digest in one cycle")


def main():
    live_timeline_lead_log_cycle()
    with tempfile.TemporaryDirectory(prefix="jkstack-helper-") as tmp:
        folder = Path(tmp)
        home = folder / "home"
        home.mkdir()
        packages = folder / "packages"
        packages.mkdir()
        env = dict(os.environ, HOME=str(home), DOTNET_CLI_HOME=str(home),
                   NUGET_PACKAGES=str(folder / "nuget-cache"), DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
                   DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
        if shutil.which("dotnet") and shutil.which("jq"):
            with zipfile.ZipFile(packages / "example.dependency.1.0.0.nupkg", "w") as package:
                package.writestr("Example.Dependency.nuspec", '<?xml version="1.0"?><package><metadata><id>Example.Dependency</id><version>1.0.0</version><authors>Example</authors><description>Synthetic fixture</description></metadata></package>')
            project = folder / "Fixture.csproj"
            project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><PackageReference Include="Example.Dependency" Version="1.0.0" /></ItemGroup></Project>')
            config = folder / "NuGet.Config"
            config.write_text('<configuration><packageSources><clear/><add key="fixture" value="' + str(packages) + '"/></packageSources></configuration>')
            subprocess.run(["dotnet", "restore", str(project), "--configfile", str(config)],
                           env=env, capture_output=True, text=True, timeout=75, check=True)
            result = subprocess.run(["bash", str(ROOT / "skills/dep-investigate/scripts/dep-snapshot.sh"),
                                     str(project), "net10.0", "Example.Dependency"], env=env,
                                    capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "Example.Dependency  requested=1.0.0  resolved=1.0.0" in result.stdout
            assert "why: Example.Dependency" in result.stdout
            assert "Fixture" in result.stdout and "1.0.0" in result.stdout
            graph = next(line.split(": ", 1)[1] for line in result.stdout.splitlines() if line.startswith("Full graph JSON: "))
            shutil.rmtree(Path(graph).parent)
            print("PASS dependency helper: resolved version and provenance from a synthetic local package")
        else:
            print("SKIP dependency helper: .NET SDK 10+ and jq required")
        if shutil.which("ffmpeg"):
            video, frame = folder / "sample.mp4", folder / "frame.jpg"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=teal:s=640x320:d=1",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], capture_output=True, check=True, timeout=15)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "0.2", "-i", str(video), "-frames:v", "1",
                            "-q:v", "2", str(frame)], capture_output=True, check=True, timeout=15)
            assert frame.stat().st_size > 0
            print("PASS video frame extraction: generated local media, no downloads")
        else:
            print("SKIP video frame extraction: ffmpeg required")


if __name__ == "__main__":
    main()
