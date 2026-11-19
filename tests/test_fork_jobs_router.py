JOB_ROUTES = {
    ("GET", "/jobs"), ("GET", "/jobs/{job_id}"), ("GET", "/jobs/{job_id}/events"),
    ("GET", "/tasks/stream/{task_id}"), ("POST", "/tasks/cancel/{task_id}"),
}


def _routes(router):
    return {(m, r.path) for r in router.routes for m in getattr(r, "methods", set()) - {"HEAD"}}


def test_jobs_router_owns_job_routes():
    from api.routers import jobs
    assert _routes(jobs.router) == JOB_ROUTES


def test_dub_export_no_longer_has_them():
    from api.routers import dub_export
    assert not (_routes(dub_export.router) & JOB_ROUTES)
