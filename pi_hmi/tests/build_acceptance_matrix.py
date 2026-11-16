"""Derive traceability from the preserved provisional official matrix; no approvals."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOFTWARE={
 'SR-PLT-02':('grow_service.py','test_m4.py','Profiles/cycles only; 60-day biological survival/size demonstration absent'),
 'SR-WAT-03':('grow_service.py','m9_endurance.py','Synthetic schedules do not measure 72-hour reservoir reserve'),
 'SR-LGT-01':('grow_service.py','test_m4.py','Synthetic timing only; approved crop settings, PPFD and photoperiod measurement absent'),
 'SR-ENV-01':('sensor_policy.py','test_m1.py','No approved canopy interface/calibration or five-minute thermal alarm acceptance'),
 'SR-ENV-02':('sensor_policy.py','test_m1.py','No approved RH interface/calibration or ten-minute band alarm acceptance'),
 'SR-ENV-03':('state_service.py','test_m1.py','Electronics sensor/thermal loads and independent cutoff unresolved; target load test absent'),
 'SR-AUT-01':('host_lifecycle.py','m9_endurance.py','72 accelerated synthetic hours are not 72 real elapsed hours or unattended physical endurance'),
 'SR-AUT-02':('restart_service.py','test_m8.py','Software inhibition/recovery only; electrical de-energization and target two-minute startup unverified'),
 'SR-DAT-01':('sqlite_repository.py','test_m8.py','Local synthetic contracts only; Pi installation and approved local model remain gated'),
 'SR-DAT-02':('storage_service.py','test_m7.py','Retention conflict unresolved: 90-day records/hourly images versus 80% cleanup preserving 30-day images; automatic deletion prohibited'),
 'SR-DAT-03':('event_service.py','m9_endurance.py','Synthetic provenance/records only; physical cadence/missing-record rate and unavailable inputs require target evidence'),
 'SR-UI-01':('host_lifecycle.py','browser_m9.cjs','Five novice users/orientation/task timing/error acceptance not performed'),
 'SR-UI-02':('grow_service.py','browser_m9.cjs','Synthetic UI only; physical readings, target refresh latency and touch usability unverified'),
 'SR-UI-03':('command_service.py','test_m4.py','Host confirmations/profiles only; crop timings and physical controls require approval'),
 'SR-ML-01':('local_ml_service.py','test_m5.py','Synthetic adapter only; approved model/runtime, target size and ten-second performance absent'),
 'SR-ML-02':('model_contract.py','test_m5.py','No approved model, held-out dataset, measured accuracy/recall/F1 or leakage audit'),
 'SR-ML-03':('local_ml_service.py','test_m5.py','Rules tested for reviewed synthetic labels only; plant classifications/models remain unapproved'),
 'SR-NET-01':('host_lifecycle.py','test_m8.py','Offline host only; remote channel delivery/unsent alarm queue not implemented or authorized'),
 'SR-SAF-01':('state_service.py','test_m1.py','Reporting/latching only; physical E-stop removal within one second requires electrical verification'),
 'SR-SAF-02':('command_service.py','test_m1.py','Normalized synthetic door only; wiring/polarity and 0.5-second pump cutoff unverified'),
 'SR-SAF-03':('grow_service.py','test_m4.py','Synthetic maintenance boundary only; hazardous physical loads and human confirmation acceptance remain open'),
 'SR-SAF-07':('command_service.py','test_m1.py','Normalized leak inhibition only; two-second cutoff/500mL physical containment test absent'),
 'SR-SAF-10':('sensor_policy.py','test_m1.py','Synthetic validation only; approved interfaces/policies, actuator fallback and target fault deadlines unresolved'),
 'SR-MNT-01':('grow_service.py','test_m4.py','Maintenance trace only; seven-day interval and 15-minute human task unverified'),
 'SR-MNT-02':('grow_service.py','test_m4.py','Maintenance trace only; flow baseline, 14-day interval and 30-minute service acceptance unverified'),
 'SR-MNT-03':('grow_service.py','test_m4.py','Maintenance trace only; cleaning procedure/90-day interval/60-minute acceptance unverified'),
 'SR-LIF-02':('host_lifecycle.py','m9_endurance.py','72-hour accelerated software run is not the required 90-day no-replacement system simulation'),
}

def build():
    path=ROOT/'docs/phase0/REQUIREMENTS_BASELINE.json';baseline=json.loads(path.read_text(encoding='utf-8'))
    rows=[];objectives={}
    for r in baseline['rows'][1:]:
        ids=r[0].split(', ');wording=r[1].split(' | ')
        for po,text in zip(ids,wording):
            if po in objectives:assert objectives[po]['wording']==text
            else:objectives[po]=dict(id=po,wording=text,requirements=[],acceptance='unapproved; system acceptance open')
            objectives[po]['requirements'].append(r[2])
        implementation,test,gap=SOFTWARE.get(r[2],(None,None,'Physical/material/service-life inspection or test required; software simulation does not establish this requirement'))
        rows.append(dict(id=r[2],objectives=ids,official_wording=r[3],official_source_status=r[8],verification_methods=r[9],
          implementation=['pi_hmi/services/'+implementation] if implementation else [],
          automated_evidence=['pi_hmi/tests/'+test] if test else [],
          manual_evidence=dict(source_title=r[6],source_url=r[7],source_claim=r[5],independently_accepted=False),
          official_gap=r[10],remaining_gate=gap,host_acceptance='partial host evidence only' if test else 'outside host test scope',
          requirements_approved=False,physical_accepted=False,production_accepted=False,
          operator_checklist='docs/phase0/M9_OPERATOR_ACCEPTANCE.md'))
    assert len(rows)==40 and len({r['id'] for r in rows})==40 and len(objectives)==6
    return dict(version='m9-host-review-1',baseline_version=baseline['version'],baseline_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
      baseline_source=baseline['source_url'],baseline_approval=baseline['approval'],review='M9 host review pending; no requirement status changed',
      objectives=list(objectives.values()),requirements=rows,
      cross_cutting_evidence=['docs/evidence/m9/README.md','docs/phase0/M9_SECURITY_REVIEW.md','pi_hmi/tests/test_m9.py','pi_hmi/tests/browser_m9.cjs'])

if __name__=='__main__':
    matrix=build();base=ROOT/'docs/phase0'
    (base/'M9_ACCEPTANCE_MATRIX.json').write_text(json.dumps(matrix,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# M9 acceptance matrix','','Version `m9-host-review-1`. All six objectives and 40 system requirements retain exact official wording and source status in [structured matrix](M9_ACCEPTANCE_MATRIX.json). Baseline `'+matrix['baseline_version']+'`; controlled approval is unresolved. Source statuses remain unchanged; no row is declared physically or production accepted. Source-linked manual evidence is recorded as a claim, not independently accepted evidence.','','| Objective | Official wording | Linked requirements |','| --- | --- | --- |']
    for po in matrix['objectives']:lines.append('| '+po['id']+' | '+po['wording']+' | '+', '.join(po['requirements'])+' |')
    lines+=['','| SR | Source status | Implementation / automated evidence | Remaining acceptance gate |','| --- | --- | --- | --- |']
    for row in matrix['requirements']:
        links=row['implementation']+row['automated_evidence']
        lines.append('| '+row['id']+' | '+row['official_source_status']+' | '+(' / '.join('['+Path(p).name+'](../../'+p+')' for p in links) if links else 'Physical/manual only')+' | '+row['remaining_gate']+' |')
    lines+=['','Cross-cutting [security review](M9_SECURITY_REVIEW.md), [operator acceptance checklist](M9_OPERATOR_ACCEPTANCE.md), [test evidence](../evidence/m9/README.md). Provisional requirements, physical measurements, approved model/crop settings, production security and retention remain gated.','']
    (base/'M9_ACCEPTANCE_MATRIX.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Traced 6 objectives and 40 unchanged provisional system requirements')
