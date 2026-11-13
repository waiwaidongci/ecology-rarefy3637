from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.schemas.upload import BatchUpload,ConflictResolution
from src.services import uploads
router=APIRouter()
@router.get('/uploads')
def index(db:Session=Depends(get_db),user=Depends(current_user)):return uploads.list_batches(db)
@router.get('/uploads/{batch_id}')
def detail(batch_id:int,db:Session=Depends(get_db),user=Depends(current_user)):return uploads.get_batch(db,batch_id)
@router.post('/uploads',status_code=200)
def submit(data:BatchUpload,db:Session=Depends(get_db),user=Depends(writers)):return uploads.submit_batch(db,data,user)
@router.post('/upload-items/{item_id}/resolution',status_code=200)
def resolve(item_id:int,data:ConflictResolution,db:Session=Depends(get_db),user=Depends(writers)):return uploads.resolve_conflict(db,item_id,data.decision,data.note,user)
