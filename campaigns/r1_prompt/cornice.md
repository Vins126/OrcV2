## How to deliver the site

These rules are the same for every task.

- Build the site in the current working directory (the workspace) by writing files there. Do not answer with code
  blocks only: only the files in the workspace are delivered.
- Put a `start.sh` in the root of the workspace; it is run with `bash start.sh`. It must start the site in the
  foreground and serve it on port 8080 (`http://localhost:8080/`). Any technology is allowed: static files, Node, Python, a framework.
- Install dependencies and run any build step now, inside the workspace. If you install dependencies, keep the
  lockfile (`package-lock.json` or equivalent; pinned versions for Python). `start.sh` must only start the site: it
  must not install or download anything, and the site must answer within 60 seconds.
- The site is opened without network access. Do not load anything from a CDN or another external host (JS
  libraries, styles, fonts, images, APIs): everything the page uses must come from the workspace.
- Every element listed under "data-testid markers" must carry exactly that `data-testid` attribute. An element
  that appears several times (for example one card per item) carries the same value on every copy.
- Whenever the user picks a date and a time, use a single `<input type="datetime-local">` (date and time in the same
  field).
- If the task has a routes contract, implement it exactly: paths, field names, JSON shapes and status codes. The
  internal structure of the server is up to you. Store the data where the contract says, inside the workspace, so
  that it survives a restart of `start.sh`.
