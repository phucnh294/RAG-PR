---
name: run-hello
description: Build the project's Docker image, run it as a container, and verify the output contains "Hello". Use when the user asks to build/deploy the Docker image, run the hello check, or verify the container prints "Hello".
---

# Run Hello

Build a Docker image from this project, deploy it as a container, and verify the container output contains the string `Hello`. If it does not, surface an error along with the container logs.

## Steps

1. **Locate the Dockerfile**
   - Look for a `Dockerfile` in the project root.
   - If none exists, stop and tell the user a `Dockerfile` is required before this skill can run — do not silently fabricate one.

2. **Build the image**
   ```bash
   docker build -t run-hello:latest .
   ```
   - If the build fails, show the build output/error to the user and stop. Do not proceed to run a broken image.

3. **Run the container**
   ```bash
   docker run --rm --name run-hello-check run-hello:latest
   ```
   - Capture stdout and stderr from this run.
   - If the container fails to start (non-zero exit before producing output), capture `docker logs run-hello-check` if the container still exists, and treat this as a failure (see step 5).

4. **Check the output**
   - Search the captured stdout/stderr for the substring `Hello` (case-sensitive match on `Hello` unless the user specifies otherwise).

5. **Report result**
   - **Success** — output contains `Hello`: report success with the relevant output line(s).
   - **Failure** — output does not contain `Hello`, or the build/run step failed:
     - Show a clear error message stating the output did not contain "Hello" (or that the build/run failed).
     - Show the full captured output/logs (`docker logs <container>` if available, otherwise the captured run output) so the user can diagnose the issue.
     - Do not report success or silently retry — surface the failure clearly.

## Notes
- Use a unique/temp container name per run to avoid name collisions with a previous run.
- Clean up the container (`--rm`) so failed runs don't leave dangling containers behind.
- This skill assumes Docker is installed and the Docker daemon is running; if `docker` commands fail with a connection error, report that as the failure reason rather than attributing it to the image/output.
