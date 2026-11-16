"""Read lifecycle status and explicitly recover synthetic host services only."""
from flask import Blueprint,current_app,jsonify,request
from services.history_http import failed
lifecycle_routes=Blueprint('lifecycle',__name__)

@lifecycle_routes.get('/api/services')
def services_status():
    lifecycle=current_app.config.get('GERM_HOST_LIFECYCLE')
    if lifecycle is None:return jsonify(state='not_configured',readiness='unavailable',production_controls_enabled=False,recovery_instruction='No managed host runtime is configured. Physical integration remains disabled.'),503
    try:return jsonify(lifecycle.snapshot())
    except Exception as exc:return failed(exc)

@lifecycle_routes.post('/api/services/recover')
def services_recover():
    lifecycle=current_app.config.get('GERM_HOST_LIFECYCLE')
    if lifecycle is None:return jsonify(error='Host lifecycle is not configured'),503
    try:
        if request.get_json(silent=True)!={}:raise ValueError('Expected empty object; no configuration or permissions can be supplied')
        result=lifecycle.recover();return jsonify(result),200 if result['state']=='running' else 503
    except Exception as exc:return failed(exc)
