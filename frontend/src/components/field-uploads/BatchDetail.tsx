import {useState} from 'react';
import type {UploadBatch,UploadItem,User} from '../../types/domain';
import {UPLOAD_ITEM_STATUS} from '../../constants/enums';
import {date} from '../../utils/format';

function DiffView({item}:{item:UploadItem}){
 const d=item.diff;
 if(!d)return <small>无差异快照</small>;
 const countEntries=Object.entries(d.counts||{});
 const metaEntries=Object.entries(d.meta||{});
 if(!countEntries.length&&!metaEntries.length)return <small>内容一致</small>;
 return <div className="diff-view">
  {!!metaEntries.length&&metaEntries.map(([k,v])=><div key={k} className="diff-line"><small>{k==='name'?'样线名称':'生境说明'}</small><span className="from">{v.from}</span><i>→</i><span className="to">{v.to}</span></div>)}
  {!!countEntries.length&&countEntries.map(([k,v])=><div key={k} className="diff-line"><small>{k}</small><span className="from">{v.from}</span><i>→</i><span className="to">{v.to}</span></div>)}
 </div>;
}

function ItemRow({item,user,busy,onResolve}:{item:UploadItem;user:User;busy:boolean;onResolve:(id:number,decision:'overwrite'|'keep',note:string)=>void}){
 const [open,setOpen]=useState(item.status==='conflict');
 const [note,setNote]=useState('');
 return <>
 <tr className={'item-'+item.status}>
  <td className="mono">{item.line_no}</td>
  <td><small>{item.transect_id?('样线#'+item.transect_id+(item.current_revision?(' / 修订'+item.current_revision):'')):'未建档'}</small><strong>{item.reference??'（坏行无编号）'}</strong></td>
  <td><span className={'badge '+item.status}>{UPLOAD_ITEM_STATUS[item.status]??item.status}</span>{item.recheck_required&&<span className="badge rejected recheck-badge">需重新核对</span>}{item.drifted&&<span className="badge rejected recheck-badge">源数据已漂移</span>}</td>
  <td className="reason-cell">{item.reason}{item.resolved_by&&<small>处理人 {item.resolved_by} · {item.resolved_at?date(item.resolved_at):''}</small>}</td>
  <td><button className="text-button" onClick={()=>setOpen(!open)}>{open?'收起明细':'查看差异/快照 ↗'}</button></td>
  <td>
   {item.status==='conflict'&&user.role!=='viewer'&&<div className="resolve-box">
    <input placeholder="处理说明（可选，500字内）" value={note} onChange={e=>setNote(e.target.value)} maxLength={500}/>
    <div className="note-actions">
     <button disabled={busy} onClick={()=>onResolve(item.id,'keep',note)}>保留现行计数</button>
     <button className="primary" disabled={busy} onClick={()=>onResolve(item.id,'overwrite',note)}>确认覆盖 →</button>
    </div>
    <small className="fine">覆盖会使样线修订号+1；若确认期间源数据又被修改，系统将拒绝本次处理并刷新差异。</small>
   </div>}
   {item.status==='conflict'&&user.role==='viewer'&&<small className="fine">只读账号不可处理冲突</small>}
  </td>
 </tr>
 {open&&<tr className="detail-row"><td colSpan={6}>
   <div className="detail-grid">
    <div><small>回传内容</small><pre className="mono">{JSON.stringify(item.incoming,null,1)}</pre></div>
    <div><small>现行快照（冲突发生时）{item.existing_snapshot?.baseline_hash?' · 基线指纹已记录':''}</small><pre className="mono">{JSON.stringify(item.existing_snapshot,null,1)}</pre></div>
    <div className="diff-col"><small>逐项差异</small><DiffView item={item}/></div>
   </div>
 </td></tr>}
 </>;
}

export function BatchDetail({batch,user,busy,onClose,onResolve}:{batch:UploadBatch;user:User;busy:boolean;onClose:()=>void;onResolve:(id:number,decision:'overwrite'|'keep',note:string)=>void}){
 const s=batch.summary;
 return <section className="batch-detail">
  <div className="section-title">
   <h2>批次 {batch.batch_ref} / 回传明细</h2>
   <small>{batch.source||'未标注来源'} · {date(batch.created_at)} · 重发{batch.redeliveries}次{batch.redelivered?' · 本次为幂等重发':''}</small>
   <button onClick={onClose}>关闭明细</button>
  </div>
  <div className="summary-strip">
   <div><small>总行数</small><b>{s.total}</b></div>
   <div><small>已接收</small><b className="ok-num">{s.accepted}</b></div>
   <div><small>重复重发</small><b>{s.duplicate}</b></div>
   <div><small>待处理冲突</small><b className="warn-num">{s.conflict}</b></div>
   <div><small>已拒收</small><b className="err-num">{s.rejected}</b></div>
   <div><small>冲突已处理</small><b>{s.resolved}</b></div>
  </div>
  <div className="table-wrap"><table>
   <thead><tr><th>行号</th><th>样线</th><th>处置状态</th><th>原因 / 处理记录</th><th>差异</th><th>冲突操作</th></tr></thead>
   <tbody>{(batch.items??[]).map(i=><ItemRow key={i.id} item={i} user={user} busy={busy} onResolve={onResolve}/>)}</tbody>
  </table></div>
 </section>;
}
