"""HMI screens and read APIs; storage and ML implementations are injected below."""

from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_from_directory

from services.camera_service import IMAGE_ROOT, latest_local_manual_capture, save_manual_capture
from services.database_service import repository
from services.ml_service import ml_service
from services.sensor_service import current_readings
from services.control_runtime import get_gateway


def create_dashboard(camera, requested_states):
    ui = Blueprint("dashboard", __name__)
    latest_manual_capture = {"image": latest_local_manual_capture()}

    def storage():
        service=get_gateway().grow_service
        return service.repo if service is not None else repository

    def camera_owner():
        return camera() if callable(camera) else camera

    @ui.get("/plant")
    @ui.get("/trends")
    @ui.get("/controls")
    @ui.get("/alerts")
    @ui.get("/maintenance")
    @ui.get("/settings")
    def screen():
        name = request.path.strip("/")
        return render_template("index.html", page=name,
                               control_tab=request.args.get("tab", "lighting"))

    @ui.get("/api/state")
    def state():
        readings = current_readings()
        grow={'state':'not_configured'}
        if get_gateway().grow_service is not None:
            try:grow=get_gateway().grow_service.snapshot()
            except Exception:grow={'state':'error','error':'Grow persistence unavailable; restart inhibited'}
        operating = get_gateway().state.snapshot()
        arduino = operating['controller_connected']
        packet = operating['controller_feedback']
        owner = camera_owner()
        camera_ready = owner is not None and owner.get_frame() is not None
        database_state = storage().status
        ml_state = ml_service.status
        try:
            alerts = storage().get_active_alerts()
        except Exception:
            current_app.logger.exception("Alert read failed")
            alerts, database_state = [], "error"
        try:
            latest_ml = ml_service.get_latest_result()
            model_info = ml_service.get_model_info()
        except Exception:
            current_app.logger.exception("ML status read failed")
            latest_ml, model_info, ml_state = None, None, "error"
        requests = requested_states() if callable(requested_states) else requested_states
        readings.update(operating['sensors'])
        for name,unit in [('electronics_temperature','degC'),('water_level','normalized state'),('door','normalized state'),('leak','normalized state'),('estop','normalized state')]:
            readings.setdefault(name,dict(value=None,unit=unit,timestamp_utc=None,age_seconds=None,state='unavailable',quality_flag='missing',fault_reason='interface_unconfigured',source='No validated input'))
        highest=max(alerts,key=lambda a:({'critical':3,'warning':2,'info':1}.get(a['severity'],0),a['timestamp_utc'])) if alerts and database_state=='ready' else None
        return jsonify({
            "grow": grow,
            "data_scope": "simulation" if current_app.config.get('GERM_SIMULATION') else "restricted",
            "system_state": operating['system_state'],
            "operating_state": operating,
            "state_revision": operating['state_revision'],
            "inhibits": operating['inhibits'],
            "maintenance_banner": operating['maintenance_banner'],
            "control_boundary": {"state": "simulation" if current_app.config.get('GERM_SIMULATION') else "restricted",
                                 "enabled": bool(current_app.config.get('GERM_SIMULATION') and get_gateway().adapter.simulated and callable(current_app.config.get('GERM_CONTROL_AUTHORIZER')))},
            "estop": operating['estop'],
            "arduino": {"state": "connected" if arduino else "unavailable",
                        "packet": readings["arduino_a0"]},
            "sensors": readings,
            "camera": {"state": "ready" if camera_ready else "unavailable"},
            "database": {"state": database_state},
            "ml": {"state": ml_state,
                   "latest_result": latest_ml,
                   "model": model_info},
            "alerts": {"state": database_state,
                       "highest":highest,
                       "active": alerts if database_state == "ready" else None},
            "actuators": {name: {"state": "reported" if packet else "unavailable",
                                 "speed": packet.get('fan_speed') if packet and name == 'fan' else None,
                                 "mode": packet.get('lighting_mode') if packet and name == 'lighting' else None,
                                 "reported_state": packet.get({'lighting': 'rgb', 'fan': 'fan', 'pump': 'pump'}[name]) if packet else None,
                                 "last_request": requests[name], "physically_verified": False}
                          for name in requests},
        })

    @ui.get("/api/trends")
    def trends():
        sensor = request.args.get("sensor", "air_temperature")
        if sensor not in {"air_temperature", "humidity", "water_temperature"}:
            return jsonify({"error": "Unsupported sensor"}), 400
        points = storage().get_sensor_history(sensor, request.args.get("start"),
                                               request.args.get("end"),
                                               request.args.get("experiment_id"))
        return jsonify({"state": storage().status, "sensor": sensor, "points": points})

    @ui.get("/api/alerts")
    def alerts():
        return jsonify({"state": storage().status,
                        "active": storage().get_active_alerts(),
                        "history": storage().get_alert_history()})

    @ui.post("/api/alerts/<int:alert_id>/ack")
    def acknowledge_alert(alert_id):
        if storage().status != "ready":
            return jsonify({"error": "Alert database not configured"}), 503
        if not storage().acknowledge_alert(alert_id):
            return jsonify({"error": "Alert could not be acknowledged"}), 503
        # Acknowledgement never clears a still-active critical condition.
        return jsonify({"ok": True, "alert_id": alert_id})

    @ui.get("/api/experiments")
    def experiments():
        return jsonify({"state": storage().status, "items": storage().get_experiments()})

    @ui.get("/api/captures")
    def captures():
        return jsonify({"state": storage().status,
                        "recent": storage().get_recent_images(),
                        "latest_manual": latest_manual_capture["image"]})

    @ui.post("/api/camera/capture")
    def manual_capture():
        owner = camera_owner()
        frame = owner.get_frame() if owner is not None else None
        if frame is None:
            return jsonify({"ok": False, "error": "Camera unavailable"}), 503
        try:
            image = save_manual_capture(frame)
        except OSError:
            current_app.logger.exception("Manual capture save failed")
            return jsonify({"ok": False, "error": "Could not save camera image"}), 500
        try:
            image_id = storage().record_image(image)
        except Exception:
            current_app.logger.exception("Capture saved but SQL indexing failed")
            image_id = None
        image["image_id"] = image_id
        image["indexed"] = image_id is not None
        image["url"] = "/captures/" + image["file_path"]
        latest_manual_capture["image"] = image
        return jsonify({"ok": True, "image": image}), 201

    @ui.get("/captures/<path:relative_path>")
    def captured_image(relative_path):
        return send_from_directory(IMAGE_ROOT, relative_path)

    return ui
