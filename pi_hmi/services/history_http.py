"""Host history routes; existing application POST restrictions apply unchanged."""
from flask import Blueprint,Response,current_app,jsonify,request
from services.history_export import ExportBusy

history_routes=Blueprint('history',__name__)

def service():
    result=current_app.config.get('GERM_HISTORY_SERVICE')
    if result is None:raise RuntimeError('History service is not configured')
    return result

def failed(exc):
    if isinstance(exc,LookupError):return jsonify(state='unavailable',error=str(exc)),404
    if isinstance(exc,ValueError):return jsonify(state='error',error=str(exc)),400
    if isinstance(exc,ExportBusy):return jsonify(state='busy',error=str(exc)),503
    return jsonify(state='unavailable',error='History/export storage unavailable; completion not acknowledged'),503

@history_routes.get('/api/history/<resource>')
def history_page(resource):
    try:
        if any(len(request.args.getlist(k))!=1 for k in request.args):raise ValueError('Duplicate query parameters')
        query=dict(request.args);limit=query.pop('limit','100');cursor=query.pop('cursor',None)
        if not limit.isdigit():raise ValueError('Invalid page size')
        return jsonify(service().history.page(resource,query,limit=int(limit),cursor=cursor))
    except Exception as exc:return failed(exc)

@history_routes.post('/api/exports')
def export_start():
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'request_id','definition'}:raise ValueError('Expected request_id and definition')
        return jsonify(service().start(data['request_id'],data['definition'])),202
    except Exception as exc:return failed(exc)

@history_routes.get('/api/history/images/<int:image_id>/file')
def history_image(image_id):
    try:
        exporter=service();row=exporter.repo.image(image_id);data=exporter._image(row)
        response=Response(data,mimetype='image/jpeg');response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff';response.headers['X-GERM-SHA256']=row['sha256']
        return response
    except Exception as exc:return failed(exc)

@history_routes.get('/api/exports/<request_id>')
def export_status(request_id):
    try:return jsonify(service().job(request_id))
    except Exception as exc:return failed(exc)

@history_routes.post('/api/exports/<request_id>/retry')
def export_retry(request_id):
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'retry'} or data['retry'] is not True:raise ValueError('Expected explicit retry true')
        exporter=service();job=exporter.job(request_id)
        return jsonify(exporter.start(request_id,job['definition'],retry=True)),202
    except Exception as exc:return failed(exc)

@history_routes.get('/api/exports/<request_id>/download')
def export_download(request_id):
    try:
        data,result=service().download(request_id)
        response=Response(data,mimetype='application/zip')
        response.headers['Content-Disposition']='attachment; filename="germ-history-'+request_id+'.zip"'
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-GERM-SHA256']=result['sha256'];response.headers['X-GERM-Export-Status']=result['status']
        return response
    except Exception as exc:return failed(exc)
