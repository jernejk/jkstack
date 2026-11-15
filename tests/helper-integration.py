#!/usr/bin/env python3
"""Integration checks with a local NuGet source and generated video; no network sources."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
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
