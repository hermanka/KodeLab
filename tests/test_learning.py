from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.contracts import CaseResult, JudgeResult
from app.db import session
from app.learning import PathInput
from app.models import Completion, PathEnrollment
from app.providers import CustomProvider
from app.tasks import run_attempt
from tests.test_api_tasks import client
from tests.test_accounts_content import account, course, draft, fake_judge, validate


def setup_path(admin, monkeypatch, optional=False):
    teacher,_=account(admin,'teacher_path','teacher')
    student,user=account(admin,'student_path','student')
    cid=course(teacher, public=True)
    teacher.post(f'/courses/{cid}/members',json={'user_id':user['id']})
    lessons=[]
    for title in ('Mengenal input','Memahami penjumlahan'):
        r=teacher.post(f'/author/courses/{cid}/lessons',json={'title':title,'body_markdown':'# Materi\nPenjelasan.'})
        assert r.status_code==201,r.text
        v=r.json();assert teacher.post(f"/author/lesson-versions/{v['id']}/publish",json={'edit_revision':1}).status_code==200
        lessons.append(v)
    problem=draft(teacher,cid);fake_judge(monkeypatch);validate(teacher,problem)
    assert teacher.post(f"/author/problem-versions/{problem['id']}/publish",json={'edit_revision':1}).status_code==200
    payload={'title':'Dasar C/C++','description':'Belajar bertahap.','languages':['c17','cpp17'],'sequential':True,'steps':[
        {'key':'intro','title':'Mengenal input','module':'Fondasi','kind':'reading','lesson_version_id':lessons[0]['id']},
        {'key':'concept','title':'Memahami penjumlahan','module':'Fondasi','kind':'reading','lesson_version_id':lessons[1]['id'],'required':not optional},
        {'key':'sum','title':'Jumlah dua bilangan','module':'Latihan','kind':'exercise','problem_version_id':problem['id']},
    ]}
    response=teacher.post(f'/author/courses/{cid}/paths',json=payload)
    assert response.status_code==201,response.text
    path=response.json();assert teacher.post(f"/author/path-versions/{path['id']}/publish",json={'edit_revision':1}).status_code==200
    return teacher,student,cid,path,problem,payload


def enroll(student,path):
    response=student.post(f"/paths/{path['path_id']}/enroll")
    assert response.status_code==200,response.text
    return response.json()


def read_all(student,enrollment):
    for step in enrollment['steps']:
        if step['kind']=='reading':
            r=student.post(f"/enrollments/{enrollment['id']}/steps/{step['id']}/complete")
            assert r.status_code==200,r.text


def stub_results(monkeypatch, accepted=True):
    def submit(self,request,key):
        verdict='EXECUTED' if request.mode=='run' else 'ACCEPTED' if accepted else 'WRONG_ANSWER'
        self._reference=key
        self._result=JudgeResult(verdict=verdict,cases=[CaseResult(id=c.id,verdict=verdict) for c in request.cases])
        return key
    monkeypatch.setattr(CustomProvider,'submit',submit)


def submission_body(enrollment,problem):
    return {'language':'c17','source':'int main(){}','problem_version_id':problem['id'],
            'enrollment_id':enrollment['id'],'path_step_id':enrollment['steps'][-1]['id']}


def test_cycle_unknown_and_duplicate_step_validation():
    base={'title':'Test','sequential':False,'steps':[
        {'key':'a','title':'A','kind':'reading','lesson_version_id':str(uuid4()),'prerequisites':['b']},
        {'key':'b','title':'B','kind':'reading','lesson_version_id':str(uuid4()),'prerequisites':['a']}]}
    with pytest.raises(ValueError,match='cycle'):PathInput(**base)
    base['steps'][1]['prerequisites']=[]
    assert PathInput(**base)
    with pytest.raises(ValueError,match='cycle'):PathInput(**{**base,'sequential':True})
    base['steps'][0]['prerequisites']=['unknown']
    with pytest.raises(ValueError,match='Unknown'):PathInput(**base)
    base['steps'][0]['prerequisites']=[];base['steps'][1]['key']='a'
    with pytest.raises(ValueError,match='Duplicate'):PathInput(**base)


def test_locked_steps_and_direct_api_bypass_are_rejected(client,monkeypatch):
    teacher,student,cid,path,problem,_=setup_path(client,monkeypatch)
    e=enroll(student,path);first,second,exercise=e['steps']
    assert not first['locked'] and second['locked'] and exercise['locked']
    assert student.get(f"/enrollments/{e['id']}/steps/{second['id']}").status_code==403
    assert student.get(f"/problems/{problem['id']}").status_code==403
    assert problem['id'] not in [p['id'] for p in student.get('/problems').json()]
    assert student.get(f'/courses/{cid}/lessons').json()==[]
    assert student.post('/submissions',json=submission_body(e,problem)).status_code==403
    assert student.post('/submissions',json={'language':'c17','source':'int main(){}','problem_version_id':problem['id']}).status_code==403
    response=student.post(f"/enrollments/{e['id']}/steps/{first['id']}/complete")
    assert response.status_code==200 and response.json()['progress']==33
    assert student.get(f"/enrollments/{e['id']}/steps/{second['id']}").status_code==200
    assert student.post(f"/enrollments/{e['id']}/steps/{first['id']}/complete").json()['progress']==33
    with session() as db:assert db.scalar(select(func.count()).select_from(Completion))==1


def test_only_accepted_official_submission_completes_exercise(client,monkeypatch):
    teacher,student,cid,path,problem,_=setup_path(client,monkeypatch)
    e=enroll(student,path);read_all(student,e)
    body=submission_body(e,problem)
    assert student.post(f"/enrollments/{e['id']}/steps/{e['steps'][-1]['id']}/complete").status_code==409
    stub_results(monkeypatch)
    row=student.post('/runs',json={**body,'input':'2 3'}).json();run_attempt.run(row['attempt_id'])
    assert student.get(f"/enrollments/{e['id']}").json()['progress']==67
    stub_results(monkeypatch,False)
    row=student.post('/submissions',json=body).json();run_attempt.run(row['attempt_id'])
    assert student.get(f"/enrollments/{e['id']}").json()['progress']==67
    stub_results(monkeypatch)
    row=student.post('/submissions',json=body).json();run_attempt.run(row['attempt_id']);run_attempt.run(row['attempt_id'])
    result=student.get(f"/enrollments/{e['id']}").json()
    assert result['complete'] and result['progress']==100 and result['completed_count']==3
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Completion))==3
        assert db.scalar(select(Completion).where(Completion.step_id==e['steps'][-1]['id'])).attempt_id==row['attempt_id']


def test_optional_steps_do_not_block_completion(client,monkeypatch):
    _,student,_,path,problem,_=setup_path(client,monkeypatch,optional=True)
    e=enroll(student,path)
    result=student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete").json()
    assert not result['steps'][-1]['locked'] and result['required_count']==2
    stub_results(monkeypatch)
    row=student.post('/submissions',json=submission_body(e,problem)).json();run_attempt.run(row['attempt_id'])
    assert student.get(f"/enrollments/{e['id']}").json()['complete']


def test_required_step_cannot_turn_optional_material_into_a_requirement():
    with pytest.raises(ValueError,match='optional'):
        PathInput(title='Path',sequential=False,steps=[
            {'key':'extra','title':'Extra','kind':'reading','lesson_version_id':str(uuid4()),'required':False},
            {'key':'required','title':'Required','kind':'reading','lesson_version_id':str(uuid4()),'prerequisites':['extra']},
        ])


def test_enrollment_ownership_and_forged_completion(client,monkeypatch):
    _,student,_,path,problem,_=setup_path(client,monkeypatch)
    other,_=account(client,'other_student','student');e=enroll(student,path)
    assert other.get(f"/enrollments/{e['id']}").status_code==404
    assert other.post('/submissions',json=submission_body(e,problem)).status_code==404
    assert student.post('/submissions',json={**submission_body(e,problem),'completed':True}).status_code==422
    assert student.post('/submissions',json={'language':'c17','source':'x','enrollment_id':e['id']}).status_code==422
    read_all(student,e)
    assert student.post('/submissions',json={**submission_body(e,problem),'problem_version_id':'sum-v1'}).status_code==422


def test_new_path_publication_preserves_enrollment_version(client,monkeypatch):
    teacher,student,cid,path,problem,payload=setup_path(client,monkeypatch)
    e=enroll(student,path);student.post(f"/enrollments/{e['id']}/steps/{e['steps'][0]['id']}/complete")
    revision=teacher.post(f"/author/paths/{path['path_id']}/versions").json()
    assert revision['revision']==2
    assert teacher.post(f"/author/path-versions/{revision['id']}/publish",json={'edit_revision':1}).status_code==200
    assert enroll(student,path)['path_version_id']==path['id']
    assert student.get(f"/enrollments/{e['id']}").json()['progress']==33
    newer,_=account(client,'student_new_version','student');new_e=enroll(newer,path)
    assert new_e['path_version_id']==revision['id'] and new_e['progress']==0
    assert teacher.put(f"/author/path-versions/{path['id']}",json={**payload,'edit_revision':1}).status_code==409


def test_revocation_and_archive_preserve_history_without_new_access(client,monkeypatch):
    teacher,student,cid,path,_,_=setup_path(client,monkeypatch)
    e=enroll(student,path)
    assert teacher.post(f"/author/paths/{path['path_id']}/archive").status_code==200
    assert student.get(f"/enrollments/{e['id']}").status_code==200
    other,_=account(client,'student_archive','student')
    assert other.post(f"/paths/{path['path_id']}/enroll").status_code==404
    uid=student.get('/auth/me').json()['id']
    assert teacher.delete(f'/courses/{cid}/members/{uid}').status_code==200
    assert student.get(f"/enrollments/{e['id']}").status_code==404
    assert student.get('/my/learning').json()==[]


def test_class_scope_and_reference_validation_on_path_authoring(client,monkeypatch):
    teacher,student,cid,path,_,payload=setup_path(client,monkeypatch)
    other,_=account(client,'other_teacher_path','teacher')
    assert other.get(f"/author/path-versions/{path['id']}").status_code==404
    assert student.get(f'/author/courses/{cid}/progress').status_code==404
    foreign=course(teacher)
    response=teacher.post(f'/author/courses/{foreign}/paths',json=payload)
    assert response.status_code==422
    rows=teacher.get(f'/author/courses/{cid}/progress').json()
    assert len(rows)==1 and rows[0]['progress']==0 and rows[0]['started_paths']==0


def test_web_shell_serves_locally_and_has_strict_policy(client):
    response=client.get('/')
    assert response.status_code==200 and 'KodeLab' in response.text
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert 'unsafe-inline' not in response.headers['content-security-policy']
    assert client.get('/assets/app.js').status_code==200
