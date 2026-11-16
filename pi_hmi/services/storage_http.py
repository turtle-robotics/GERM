"""Host-only storage API. Application-wide mutation authorization is unchanged."""
from flask import Blueprint,Response,current_app,jsonify,request
from services.history_http import failed

storage_routes=Blueprint('storage',__name__)

def service():
    result=current_app.config.get('GERM_STORAGE_SERVICE')
    if result is None:raise RuntimeError('Storage service not configured')
    return result

@storage_routes.get('/api/storage')
def storage_inventory():
    try:return jsonify(service().inventory())
    except Exception as exc:return failed(exc)

@storage_routes.post('/api/storage/jobs')
def storage_start():
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'request_id','definition'}:raise ValueError('Expected request_id and definition')
        return jsonify(service().start(data['request_id'],data['definition'])),202
    except Exception as exc:return failed(exc)

@storage_routes.get('/api/storage/jobs/<request_id>')
def storage_status(request_id):
    try:return jsonify(service().job(request_id))
    except Exception as exc:return failed(exc)

@storage_routes.post('/api/storage/jobs/<request_id>/retry')
def storage_retry(request_id):
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'retry'} or data['retry'] is not True:raise ValueError('Explicit retry true required')
        storage=service();job=storage.job(request_id)
        return jsonify(storage.start(request_id,job['definition'],retry=True)),202
    except Exception as exc:return failed(exc)

@storage_routes.get('/api/storage/jobs/<request_id>/download')
def storage_download(request_id):
    try:
        data,result=service().download(request_id)
        response=Response(data,mimetype='application/zip');response.headers['Cache-Control']='no-store'
        response.headers['Content-Disposition']='attachment; filename="germ-backup-'+request_id+'.zip"'
        response.headers['X-Content-Type-Options']='nosniff';response.headers['X-GERM-SHA256']=result['sha256']
        return response
    except Exception as exc:return failed(exc)
