"""Serialize model/reference mutations in the single supported local server.

Read pages and capture/release traffic never acquire this gate. Worker model
registration writes a new training-owned artifact; it does not delete an input
model. Offline import/maintenance tools must run with the server stopped.
"""


def coordinates(method,path):
    if method in {'GET','HEAD','OPTIONS'}:return False
    return any(path==prefix or path.startswith(prefix+'/') for prefix in (
        '/api/models','/api/jobs','/api/training','/api/evaluations','/api/datasets','/api/workflow','/api/clinical/plans'))
