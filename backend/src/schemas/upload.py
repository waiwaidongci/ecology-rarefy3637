from typing import Any
from pydantic import BaseModel,Field
class BatchUpload(BaseModel):
 batch_ref:str=Field(min_length=1,max_length=80)
 survey_id:int=Field(gt=0)
 source:str=Field(default='',max_length=120)
 items:list[Any]=Field(min_length=1,max_length=200)
class ConflictResolution(BaseModel):
 decision:str=Field(pattern='^(overwrite|keep)$')
 note:str=Field(default='',max_length=500)
