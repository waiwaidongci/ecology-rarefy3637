import os,sys,tempfile,threading
from datetime import date
os.environ['JWT_SECRET']='test-secret'
_TMP=tempfile.mkdtemp(prefix='upload-conc-')
os.environ['DATABASE_URL']='sqlite:///'+_TMP+'/conc.db'
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))

from src.config.database import Base,engine,SessionLocal
from src.models import *
from src.services import uploads
from src.utils.security import hash_password

Base.metadata.create_all(engine)
with SessionLocal() as db:
 u=User(email='a@songji.demo',name='A',role='admin',password_hash=hash_password('pw'))
 s=Survey(name='期',survey_date=date(2026,10,14),filename='f.csv')
 db.add_all([u,s]);db.commit();UID=u.id;SID=s.id

def mkitem(ref,count):
 return {'reference':ref,'name':'N'+ref,'habitat':'林缘','counts':[{'species':'S01','count':count}]}

from src.schemas.upload import BatchUpload
PASS=0;FAIL=0
def check(n,c,d=''):
 global PASS,FAIL
 if c:PASS+=1;print('  PASS',n)
 else:FAIL+=1;print('  FAIL',n,d)

print('== C1. 两个线程同时回传同一新样线编号（不同内容）：只能建档一次，另一方进冲突 ==')
results=[];barrier=threading.Barrier(2)
def worker(batch_ref,count):
 try:
  barrier.wait()
  with SessionLocal() as db:
   user=db.get(User,UID)
   data=BatchUpload(batch_ref=batch_ref,survey_id=SID,items=[mkitem('SJ-RACE',count)])
   results.append(uploads.submit_batch(db,data,user))
 except Exception as e:
  results.append({'error':type(e).__name__+': '+str(e)[:120]})
t1=threading.Thread(target=worker,args=('R-1',11));t2=threading.Thread(target=worker,args=('R-2',22))
t1.start();t2.start();t1.join();t2.join()
errs=[r for r in results if 'error' in r]
check('两个线程都未报未处理异常',not errs,str(errs))
if not errs:
 statuses=sorted(i['status'] for r in results for i in r['items'])
 check('一个accepted一个conflict',statuses==['accepted','conflict'],str(statuses))
 with SessionLocal() as db:
  ts=db.scalars(__import__('sqlalchemy').select(Transect).where(Transect.reference=='SJ-RACE')).all()
  check('样线只建档一次',len(ts)==1,str(len(ts)))

print('== C2. 两个线程同时回传相同批次号相同内容：幂等，只生成一个批次 ==')
payload={'batch_ref':'REDUP','survey_id':SID,'source':'x','items':[mkitem('SJ-DUP',3)]}
results2=[];barrier2=threading.Barrier(2)
def worker2():
 try:
  barrier2.wait()
  with SessionLocal() as db:
   user=db.get(User,UID)
   results2.append(uploads.submit_batch(db,BatchUpload(**payload),user))
 except Exception as e:
  results2.append({'error':type(e).__name__+': '+str(e)[:120]})
ta=threading.Thread(target=worker2);tb=threading.Thread(target=worker2);ta.start();tb.start();ta.join();tb.join()
errs=[r for r in results2 if 'error' in r]
check('重发线程未崩溃',not errs,str(errs))
if not errs:
 with SessionLocal() as db:
  from sqlalchemy import select,func
  n=db.scalar(select(func.count()).select_from(UploadBatch).where(UploadBatch.batch_ref=='REDUP'))
  check('批次只建一条',n==1,str(n))
  nt=db.scalar(select(func.count()).select_from(Transect).where(Transect.reference=='SJ-DUP'))
  check('样线只建一条',nt==1,str(nt))
  b=db.scalar(select(UploadBatch).where(UploadBatch.batch_ref=='REDUP'))
  check('redeliveries计入并发重发',b.redeliveries>=1,str(b.redeliveries))

print('== C3. 批次内混合新样线与并发冲突：可接收行保留、冲突不拖垮后续行 ==')
from src.services import uploads as up
from src.models import Transect as TModel
with SessionLocal() as db:
 user=db.get(User,UID)
 b1=up.submit_batch(db,BatchUpload(batch_ref='R-3A',survey_id=SID,items=[mkitem('SJ-KEEP',5)]),user)
 check('前置批次正常接收',b1['summary']['accepted']==1)
 # 并发赢家在独立会话先建好同编号样线并提交（内容与即将回传的不同）
 other=SessionLocal()
 try:
  other.add(TModel(survey_id=SID,reference='SJ-RACE2',name='赢家',habitat='林缘',revision=1,
           content_hash=up.content_hash('SJ-RACE2','赢家','林缘',{'S01':1})));other.commit()
 finally:
  other.close()
 # 同批内含：撞号冲突线 + 正常新线；校验逐项处置且后续行不受影响
 b2=up.submit_batch(db,BatchUpload(batch_ref='R-3B',survey_id=SID,items=[mkitem('SJ-RACE2',8),mkitem('SJ-AFTER',9)]),user)
 statuses={i['reference']:i['status'] for i in b2['items']}
 check('冲突线进入conflict而非丢行',statuses.get('SJ-RACE2')=='conflict',str(statuses))
 check('后续新样线仍正常接收',statuses.get('SJ-AFTER')=='accepted',str(statuses))
 check('前置批次明细未被回滚',up.get_batch(db,b1['id'])['summary']['accepted']==1)
 check('冲突线原因说明并发建档',any('另一组建档' in i['reason'] or '旧副本不覆盖' in i['reason'] for i in b2['items'] if i['reference']=='SJ-RACE2'))

print(f'\n结果：{PASS} 通过 / {FAIL} 失败')
sys.exit(1 if FAIL else 0)
