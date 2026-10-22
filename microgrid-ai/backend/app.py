"""Flask application entry point.

    python -m backend.app            # serve on http://0.0.0.0:5000
    python -m backend.app --port 8000

The dashboard is served from ``templates/`` + ``static/`` by the same process
that answers the API, so the browser talks to the real ingestion/storage/model
pipeline with no cross-origin setup.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db  # noqa: E402
from backend.api.routes import api  # noqa: E402
from backend.services import demo_feed  # noqa: E402
from config import settings  # noqa: E402


def create_app(start_demo_feed: bool = True) -> Flask:
    settings.ensure_directories()
    db.connect()

    app = Flask(
        __name__,
        template_folder=str(settings.TEMPLATES_DIR),
        static_folder=str(settings.STATIC_DIR),
        static_url_path="/static",
    )
    app.config.update(
        JSON_SORT_KEYS=False,
        SECRET_KEY=settings.SECRET_KEY,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )

    app.register_blueprint(api)

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/favicon.ico")
    def favicon():
        icon = settings.STATIC_DIR / "img" / "favicon.svg"
        if icon.exists():
            return app.send_static_file("img/favicon.svg")
        return ("", 204)

    @app.get("/reports/graphs/<path:filename>")
    def report_graph(filename):
        """Serve the analysis figures produced by ``python -m ml.graphs``.

        The files live in ``reports/graphs`` rather than ``static`` so that the
        generated report assets stay in one place; this route is read-only and
        restricted to that directory.
        """
        return send_from_directory(str(settings.GRAPHS_DIR), filename)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({
            "status": "error",
            "error": {"code": "not_found",
                      "message": "No route matches this URL."},
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({
            "status": "error",
            "error": {"code": "method_not_allowed",
                      "message": "This method is not allowed on this route."},
        }), 405

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover - defensive
        logging.exception("unhandled error: %s", error)
        return jsonify({
            "status": "error",
            "error": {"code": "internal_error",
                      "message": "Unexpected server error."},
        }), 500

    if start_demo_feed and str(db.get_setting("demo_mode", int)) == "1":
        demo_feed.FEED.start()

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=settings.HOST)
    parser.add_argument("--port", type=int, default=settings.PORT)
    parser.add_argument("--debug", action="store_true", default=settings.DEBUG)
    parser.add_argument("--no-demo-feed", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if not args.debug else logging.DEBUG,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    app = create_app(start_demo_feed=not args.no_demo_feed)

    print("Microgrid AI platform")
    print("  dashboard : http://127.0.0.1:%d/" % args.port)
    print("  API health: http://127.0.0.1:%d/api/health" % args.port)
    print("  database  : %s" % db.db_path())
    print("  readings  : %d" % db.reading_count())
    if db.get_setting("demo_mode", int) == 1:
        print("  data mode : TEST (sample telemetry is tagged 'test')")
    print("Press Ctrl+C to stop.")

    app.run(host=args.host, port=args.port, debug=args.debug,
            use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
