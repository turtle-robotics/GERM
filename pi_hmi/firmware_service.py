"""Firmware entry path shares the gateway; real flashing is not enabled in M1."""
import secrets
from flask import Blueprint, g, jsonify, render_template, request
from services.control_runtime import get_gateway


def create_firmware_blueprint(token=None):
    ui = Blueprint('firmware', __name__)
    token = token or secrets.token_urlsafe(32)

    @ui.app_context_processor
    def firmware_context():
        return {'firmware_token': token}

    @ui.get('/firmware')
    def screen():
        return render_template('firmware.html', token=token)

    @ui.post('/api/firmware')
    def upload():
        if not secrets.compare_digest(request.headers.get('X-GERM-Token', ''), token):
            return jsonify(error='Reload the local firmware page first'), 403
        if request.files.get('firmware') is not None:
            return jsonify(status='restricted', error='Custom firmware safety behavior has not been reviewed'), 403
        try:
            gateway = get_gateway()
            context = {k: request.form[k] for k in ('confirmation_id', 'request_id') if k in request.form}
            if 'expected_state_revision' in request.form:
                context['expected_state_revision'] = int(request.form['expected_state_revision'])
            intent = gateway.intent('firmware_update', {'mode': request.form.get('mode', 'normal')}, **context)
            result = gateway.execute(intent, getattr(g, 'control_authority', None))
            if not result['allowed']:
                result['error'] = '; '.join(result['reason_codes'])
            return jsonify(result), result['http_status']
        except (ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400

    return ui
