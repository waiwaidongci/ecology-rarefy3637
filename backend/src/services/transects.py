from sqlalchemy import select
from fastapi import HTTPException
from src.models import Survey,Transect,SpeciesCount
from src.utils.serialize import row
from .audit import record
from .uploads import content_hash
def get_counts(db,id):return {x.species:x.count for x in db.scalars(select(SpeciesCount).where(SpeciesCount.transect_id==id).order_by(SpeciesCount.species))}
def list_transects(db,survey_id=None):
 q=select(Transect).order_by(Transect.survey_id,Transect.reference)
 if survey_id is not None:q=q.where(Transect.survey_id==survey_id)
 return [dict(row(t),counts=get_counts(db,t.id),n=sum(get_counts(db,t.id).values())) for t in db.scalars(q)]
def create_transect(db,data,user):
 if not db.get(Survey,data.survey_id):raise HTTPException(404,'调查期不存在')
 if db.scalar(select(Transect).where(Transect.survey_id==data.survey_id,Transect.reference==data.reference)):raise HTTPException(409,'调查期内样线编号已存在')
 counts={x.species:x.count for x in data.counts}
 obj=Transect(**data.model_dump(exclude={'counts'}),revision=1,content_hash=content_hash(data.reference,data.name,data.habitat,counts));db.add(obj);db.flush();db.add_all([SpeciesCount(transect_id=obj.id,**x.model_dump()) for x in data.counts]);db.commit();record(db,user.email,'transect.create',{'transect_id':obj.id});return row(obj)
