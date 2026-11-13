import json,hashlib
from datetime import datetime,timezone
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models import Survey,Transect,SpeciesCount,UploadBatch,UploadItem
from src.constants.species import SPECIES
from src.constants.enums import BatchStatus,ItemStatus
from src.utils.serialize import row
from .audit import record

MAX_SPECIES_COUNT=100000
MAX_TRANSECT_TOTAL=2400000
MAX_BATCH_ITEMS=200

def content_hash(reference,name,habitat,counts):
 data={'reference':reference,'name':name,'habitat':habitat,'counts':{s:int(counts.get(s,0)) for s in sorted(SPECIES)}}
 return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def payload_hash(payload):
 return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def validate_item(raw):
 if not isinstance(raw,dict):return None,'坏行：每行必须是JSON对象'
 ref=raw.get('reference');name=raw.get('name');habitat=raw.get('habitat')
 if not isinstance(ref,str) or not ref.strip() or len(ref)>50:return None,'样线编号缺失或长度超限（1-50）'
 if not isinstance(name,str) or not name.strip() or len(name)>100:return None,'样线名称缺失或长度超限（1-100）'
 if not isinstance(habitat,str) or not habitat.strip() or len(habitat)>80:return None,'生境说明缺失或长度超限（1-80）'
 counts_raw=raw.get('counts')
 if not isinstance(counts_raw,list) or not (1<=len(counts_raw)<=24):return None,'物种计数须为1-24行的数组'
 counts={};dupes=set()
 for c in counts_raw:
  if not isinstance(c,dict):return None,'计数行必须是JSON对象'
  species=c.get('species');count=c.get('count')
  if not isinstance(species,str) or species not in SPECIES:return None,f"未知物种编码：{species!r}，允许S01-S24"
  if isinstance(count,bool) or not isinstance(count,int):return None,f'{species} 计数必须是非负整数'
  if count<0:return None,f'{species} 计数不可为负'
  if count>MAX_SPECIES_COUNT:return None,f'{species} 计数超过单种上限{MAX_SPECIES_COUNT}'
  if species in counts:dupes.add(species)
  counts[species]=count
 if dupes:return None,'同样线物种不可重复（'+','.join(sorted(dupes))+'），请先汇总'
 if sum(counts.values())>MAX_TRANSECT_TOTAL:return None,f'样线个体总数超过上限{MAX_TRANSECT_TOTAL}'
 return {'reference':ref.strip(),'name':name.strip(),'habitat':habitat.strip(),'counts':counts},''

def counts_map(db,transect_id):
 return {x.species:x.count for x in db.scalars(select(SpeciesCount).where(SpeciesCount.transect_id==transect_id))}

def snapshot(db,t):
 counts=counts_map(db,t.id)
 return {'transect_id':t.id,'reference':t.reference,'name':t.name,'habitat':t.habitat,'revision':t.revision,'counts':{s:counts.get(s,0) for s in sorted(SPECIES)},'content_hash':t.content_hash,'updated_at':t.updated_at.isoformat() if t.updated_at else None}

def meta_and_count_diff(incoming,transect,db):
 existing_counts=counts_map(db,transect.id)
 count_diff={}
 for code in sorted(SPECIES):
  new=incoming['counts'].get(code,0);old=existing_counts.get(code,0)
  if new!=old:count_diff[code]={'from':old,'to':new}
 meta_diff={}
 for field in ('name','habitat'):
  old=getattr(transect,field);new=incoming[field]
  if new!=old:meta_diff[field]={'from':old,'to':new}
 return {'counts':count_diff,'meta':meta_diff}

def item_row(db,item):
 data=row(item)
 if item.status==ItemStatus.CONFLICT and item.transect_id:
  t=db.get(Transect,item.transect_id)
  snap=item.existing_snapshot or {}
  baseline=snap.get('original_hash') or snap.get('baseline_hash') or snap.get('content_hash')
  live_hash=(t.content_hash or content_hash(t.reference,t.name,t.habitat,counts_map(db,t.id))) if t else None
  data['drifted']=bool(t and baseline and live_hash!=baseline)
  data['current_revision']=t.revision if t else None
 else:data['drifted']=False
 return data

def get_batch(db,batch_id):
 batch=db.get(UploadBatch,batch_id)
 if not batch:raise HTTPException(404,'回传批次不存在')
 items=[item_row(db,x) for x in db.scalars(select(UploadItem).where(UploadItem.batch_id==batch_id).order_by(UploadItem.line_no))]
 return dict(row(batch),items=items,summary=summarize(items))

def summarize(items):
 out={'total':len(items)}
 for st in ItemStatus:out[st]=sum(1 for x in items if x['status']==st)
 return out

def list_batches(db):
 batches=db.scalars(select(UploadBatch).order_by(UploadBatch.id.desc()).limit(200)).all()
 result=[]
 for b in batches:
  items=db.scalars(select(UploadItem).where(UploadItem.batch_id==b.id)).all()
  d=row(b);d['summary']={'total':len(items)}
  for st in ItemStatus:d['summary'][st]=sum(1 for x in items if x.status==st)
  result.append(d)
 return result

def submit_batch(db,data,user):
 survey=db.get(Survey,data.survey_id)
 if not survey:raise HTTPException(404,'调查期不存在')
 if len(data.items)>MAX_BATCH_ITEMS:raise HTTPException(422,f'单批最多{MAX_BATCH_ITEMS}行')
 canonical={'batch_ref':data.batch_ref,'survey_id':data.survey_id,'source':data.source,'items':data.items}
 digest=payload_hash(canonical)
 existing=db.scalar(select(UploadBatch).where(UploadBatch.batch_ref==data.batch_ref))
 if existing:
  if existing.payload_hash!=digest:raise HTTPException(409,f'批次号 {data.batch_ref} 已用于内容不同的回传，请使用新批次号')
  existing.redeliveries+=1;db.commit()
  record(db,user.email,'upload.redelivery',{'batch_id':existing.id,'redeliveries':existing.redeliveries})
  return dict(get_batch(db,existing.id),redelivered=True)
 batch=UploadBatch(batch_ref=data.batch_ref,survey_id=data.survey_id,source=data.source,payload_hash=digest,status=BatchStatus.OPEN,creator_id=user.id)
 db.add(batch)
 try:
  db.flush();db.commit()
 except IntegrityError:
  db.rollback()
  winner=db.scalar(select(UploadBatch).where(UploadBatch.batch_ref==data.batch_ref).with_for_update())
  if winner is None:raise HTTPException(500,'回传批次写入冲突，请重试')
  if winner.payload_hash!=digest:raise HTTPException(409,f'批次号 {data.batch_ref} 已用于内容不同的回传，请使用新批次号')
  winner.redeliveries+=1;db.commit()
  record(db,user.email,'upload.redelivery',{'batch_id':winner.id,'redeliveries':winner.redeliveries,'concurrent':True})
  return dict(get_batch(db,winner.id),redelivered=True)
 batch_id=batch.id
 in_batch_refs=set()
 for line_no,raw in enumerate(data.items,start=1):
  cleaned,error=validate_item(raw)
  if error:
   db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=raw.get('reference') if isinstance(raw,dict) and isinstance(raw.get('reference'),str) else None,status=ItemStatus.REJECTED,reason=error,incoming=raw if isinstance(raw,dict) else {'raw':str(raw)[:300]}))
   continue
  if cleaned['reference'] in in_batch_refs:
   db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],status=ItemStatus.REJECTED,reason='批次内样线编号重复，需先合并后再回传',incoming=cleaned));continue
  in_batch_refs.add(cleaned['reference'])
  digest_item=content_hash(**cleaned)
  t=db.scalar(select(Transect).where(Transect.survey_id==data.survey_id,Transect.reference==cleaned['reference']).with_for_update())
  if t is None:
   new_t=Transect(survey_id=data.survey_id,reference=cleaned['reference'],name=cleaned['name'],habitat=cleaned['habitat'],revision=1,content_hash=digest_item)
   db.add(new_t)
   try:
    with db.begin_nested():
     db.flush()
   except IntegrityError:
    t=db.scalar(select(Transect).where(Transect.survey_id==data.survey_id,Transect.reference==cleaned['reference']).with_for_update())
    current_hash=t.content_hash or content_hash(t.reference,t.name,t.habitat,counts_map(db,t.id))
    snap=snapshot(db,t);snap['baseline_hash']=current_hash;snap['original_hash']=current_hash
    if current_hash==digest_item:
     db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],transect_id=t.id,status=ItemStatus.DUPLICATE,reason='并发回传内容与现行计数一致，按重复重发处理，不新增计数与修订号',incoming=cleaned,existing_snapshot=snap,content_hash=digest_item))
    else:
     db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],transect_id=t.id,status=ItemStatus.CONFLICT,reason='并发回传时同编号样线已由另一组建档；旧副本不覆盖新计数，等待人工确认',incoming=cleaned,existing_snapshot=snap,diff=meta_and_count_diff(cleaned,t,db),content_hash=digest_item))
    continue
   db.add_all([SpeciesCount(transect_id=new_t.id,species=s,count=c) for s,c in cleaned['counts'].items()])
   db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],transect_id=new_t.id,status=ItemStatus.ACCEPTED,reason='新样线已接收建档',incoming=cleaned,content_hash=digest_item))
   continue
  current_hash=t.content_hash or content_hash(t.reference,t.name,t.habitat,counts_map(db,t.id))
  snap=snapshot(db,t);snap['baseline_hash']=current_hash;snap['original_hash']=current_hash
  if current_hash==digest_item:
   db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],transect_id=t.id,status=ItemStatus.DUPLICATE,reason='回传内容与现行计数一致，按重复重发处理，不新增计数与修订号',incoming=cleaned,existing_snapshot=snap,content_hash=digest_item))
   continue
  diff=meta_and_count_diff(cleaned,t,db)
  db.add(UploadItem(batch_id=batch_id,line_no=line_no,reference=cleaned['reference'],transect_id=t.id,status=ItemStatus.CONFLICT,reason='同编号样线已存在且内容不同；旧副本不覆盖新计数，等待人工确认',incoming=cleaned,existing_snapshot=snap,diff=diff,content_hash=digest_item))
 open_count=db.scalar(select(func.count()).select_from(UploadItem).where(UploadItem.batch_id==batch_id,UploadItem.status==ItemStatus.CONFLICT))
 batch=db.get(UploadBatch,batch_id);batch.status=BatchStatus.OPEN if open_count else BatchStatus.CLOSED
 db.commit()
 record(db,user.email,'upload.batch',{'batch_id':batch_id,'batch_ref':batch.batch_ref,'items':len(data.items)})
 return dict(get_batch(db,batch_id),redelivered=False)

def resolve_conflict(db,item_id,decision,note,user):
 item=db.get(UploadItem,item_id)
 if not item:raise HTTPException(404,'回传明细不存在')
 if item.status!=ItemStatus.CONFLICT:raise HTTPException(409,'该明细不是待处理冲突，可能已处理或被拒收')
 t=db.get(Transect,item.transect_id) if item.transect_id else None
 if t is None:raise HTTPException(409,'关联样线已不存在，无法处理冲突')
 t=db.scalar(select(Transect).where(Transect.id==t.id).with_for_update())
 live_hash=t.content_hash or content_hash(t.reference,t.name,t.habitat,counts_map(db,t.id))
 incoming=item.incoming
 incoming_hash=content_hash(incoming['reference'],incoming['name'],incoming['habitat'],incoming['counts'])
 baseline_hash=(item.existing_snapshot or {}).get('baseline_hash') or (item.existing_snapshot or {}).get('content_hash')
 if live_hash!=baseline_hash:
  original=(item.existing_snapshot or {}).get('original_hash') or baseline_hash
  item.recheck_required=True;item.existing_snapshot={**snapshot(db,t),'baseline_hash':live_hash,'original_hash':original};item.diff=meta_and_count_diff(incoming,t,db)
  db.commit()
  record(db,user.email,'upload.conflict.recheck',{'item_id':item.id,'reason':'现行样线在确认期间已变化'})
  raise HTTPException(409,'源数据在确认期间又有变化，已拒绝本次处理并刷新差异，请重新核对后再确认')
 if incoming_hash!=item.content_hash:
  item.recheck_required=True
  db.commit()
  record(db,user.email,'upload.conflict.recheck',{'item_id':item.id,'reason':'回传明细内容被改动'})
  raise HTTPException(409,'回传明细与提交时不一致，请以原始回传重新提交或人工核对后再确认')
 if decision=='overwrite':
  existing=db.scalars(select(SpeciesCount).where(SpeciesCount.transect_id==t.id)).all()
  for sc in existing:db.delete(sc)
  db.flush()
  db.add_all([SpeciesCount(transect_id=t.id,species=s,count=c) for s,c in incoming['counts'].items()])
  t.name=incoming['name'];t.habitat=incoming['habitat'];t.revision+=1;t.content_hash=incoming_hash
  item.status=ItemStatus.RESOLVED;item.resolution='overwrite';item.reason=f'确认覆盖：修订号升至{t.revision}'+(f'；{note}' if note else '')
 else:
  item.status=ItemStatus.RESOLVED;item.resolution='keep';item.reason='确认保留现行计数，拒绝该副本'+(f'；{note}' if note else '')
 item.resolved_by=user.email;item.resolved_at=datetime.now(timezone.utc)
 open_count=db.scalar(select(func.count()).select_from(UploadItem).where(UploadItem.batch_id==item.batch_id,UploadItem.status==ItemStatus.CONFLICT))
 batch=db.get(UploadBatch,item.batch_id);batch.status=BatchStatus.OPEN if open_count else BatchStatus.CLOSED
 db.commit()
 record(db,user.email,'upload.conflict.resolved',{'item_id':item.id,'batch_id':item.batch_id,'decision':decision,'transect_id':t.id,'revision':t.revision})
 return get_batch(db,item.batch_id)
