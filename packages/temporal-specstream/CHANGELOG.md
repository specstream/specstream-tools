# Changelog

## 0.1.0

- `SpecStreamPlugin`: registers the `specstream.web_search` and `specstream.extract` Activities on a Worker.
- A refused request (a bad key, a bad argument, no credit) fails the Activity at once.
  A rate limit, a server error or a network error is left to the Activity's retry policy.
