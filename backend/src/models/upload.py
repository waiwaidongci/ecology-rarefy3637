from datetime import datetime,timezone
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,JSON,ForeignKey,DateTime,Integer,UniqueConstraint
from src.config.database import Base
class UploadBatch(Base):
 __tablename__='upload_batches'
 id:Mapped[int]=mapped_column(primary_key=True)
 batch_ref:Mapped[str]=mapped_column(String(80),unique=True)
 survey_id:Mapped[int]=mapped_column(ForeignKey('surveys.id'))
 source:Mapped[str]=mapped_column(String(120),default='')
 payload_hash:Mapped[str]=mapped_column(String(64))
 status:Mapped[str]=mapped_column(String(20),default='open')
 redeliveries:Mapped[int]=mapped_column(Integer,default=0)
 creator_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class UploadItem(Base):
 __tablename__='upload_items'
 __table_args__=(UniqueConstraint('batch_id','line_no'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 batch_id:Mapped[int]=mapped_column(ForeignKey('upload_batches.id'))
 line_no:Mapped[int]=mapped_column(Integer)
 reference:Mapped[str|None]=mapped_column(String(50),nullable=True)
 transect_id:Mapped[int|None]=mapped_column(ForeignKey('transects.id'),nullable=True)
 status:Mapped[str]=mapped_column(String(20))
 reason:Mapped[str]=mapped_column(String(500),default='')
 incoming:Mapped[dict]=mapped_column(JSON,default=dict)
 existing_snapshot:Mapped[dict|None]=mapped_column(JSON,nullable=True)
 diff:Mapped[dict|None]=mapped_column(JSON,nullable=True)
 content_hash:Mapped[str|None]=mapped_column(String(64),nullable=True)
 recheck_required:Mapped[bool]=mapped_column(default=False)
 resolution:Mapped[str|None]=mapped_column(String(20),nullable=True)
 resolved_by:Mapped[str|None]=mapped_column(String(120),nullable=True)
 resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
