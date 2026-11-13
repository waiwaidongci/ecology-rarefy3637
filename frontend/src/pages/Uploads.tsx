import {useState,useEffect,useCallback} from 'react';
import type {UploadBatch,User,Survey} from '../types/domain';
import {uploadApi} from '../api/uploads';
import {PageTitle} from '../components/common/PageTitle';
import {Notice} from '../components/common/Notice';
import {Table} from '../components/common/Table';
import {Empty} from '../components/common/Empty';
import {UPLOAD_ITEM_STATUS,UPLOAD_BATCH_STATUS} from '../constants/enums';
import {useAsync} from '../hooks/useAsync';
import {date} from '../utils/format';
import {BatchSubmitForm} from '../components/field-uploads/BatchSubmitForm';
import {BatchDetail} from '../components/field-uploads/BatchDetail';

export function UploadsPage({surveys,user,reloadCatalog}:{surveys:Survey[];user:User;reloadCatalog:()=>Promise<any>}){
 const [batches,setBatches]=useState<UploadBatch[]>([]),[error,setError]=useState(''),[selected,setSelected]=useState<UploadBatch|null>(null),[showForm,setForm]=useState(false);
 const {busy,error:actError,message,act}=useAsync();
 const reload=useCallback(async(selectId?:number)=>{
  try{
   const list=await uploadApi.batches();setBatches(list);setError('');
   const id=selectId??selected?.id;
   if(id){setSelected(await uploadApi.batch(id));}
  }catch(e){setError(e.message);}
 },[selected?.id]);
 useEffect(()=>{reload();},[reload]);
 async function openBatch(id:number){setSelected(await uploadApi.batch(id));}
 async function handleResolve(itemId:number,decision:'overwrite'|'keep',note:string){
  const b=await act(async()=>uploadApi.resolve(itemId,decision,note),decision==='overwrite'?'已按确认覆盖，修订号已递增':'已保留现行计数，副本被拒绝');
  if(b){setSelected(b);await reloadCatalog();const list=await uploadApi.batches();setBatches(list);}
 }
 return <>
  <PageTitle index="07 / FIELD UPLOAD" title="离线补录整批回传，冲突逐项处置。" description="同一期样线两组并发回传不再整批失败：新样线直接建档，相同重发不增计数，旧副本不覆盖新计数；坏行逐行拒收并注明原因，冲突经人工确认后处理，确认期间源数据再变会要求重新核对。" action={user.role!=='viewer'?<div className="actions"><button onClick={()=>setForm(!showForm)}>{showForm?'收起回传表单':'整批回传 ↗'}</button><button onClick={()=>reload()}>刷新 ↻</button></div>:<button onClick={()=>reload()}>刷新 ↻</button>}/>
  <Notice error={error||actError} message={message}/>
  {showForm&&user.role!=='viewer'&&<BatchSubmitForm surveys={surveys} busy={busy} onClose={()=>setForm(false)} onSubmitted={async(b:UploadBatch)=>{setForm(false);await reloadCatalog();await reload(b.id);setSelected(await uploadApi.batch(b.id));}}/>}
  {!batches.length&&<Empty title="还没有回传批次" help="野外两组离线补录后，通过整批回传提交JSON；系统保留可接收记录并逐项说明冲突或拒收原因。"/>}
  {!!batches.length&&<Table headers={['批次号 / 来源','调查期','状态','接收/重复/冲突/拒收/已处理','重发次数','回传时间','']}>
   {batches.map(b=><tr key={b.id} className={selected?.id===b.id?'selected':''}>
    <td><small>{b.source||'未标注来源'}</small><strong>{b.batch_ref}</strong></td>
    <td>{surveys.find(s=>s.id===b.survey_id)?.name??b.survey_id}</td>
    <td><span className={'badge '+b.status}>{UPLOAD_BATCH_STATUS[b.status]??b.status}</span></td>
    <td className="mono">{b.summary.accepted} / {b.summary.duplicate} / <b className={b.summary.conflict?'warn-num':''}>{b.summary.conflict}</b> / <b className={b.summary.rejected?'err-num':''}>{b.summary.rejected}</b> / {b.summary.resolved}</td>
    <td className="mono">{b.redeliveries}</td>
    <td className="mono">{date(b.created_at)}</td>
    <td><button className="text-button" onClick={()=>openBatch(b.id)}>回传明细 ↗</button></td>
   </tr>)}
  </Table>}
  {selected&&<BatchDetail batch={selected} user={user} busy={busy} onClose={()=>setSelected(null)} onResolve={handleResolve}/>}
 </>;
}
