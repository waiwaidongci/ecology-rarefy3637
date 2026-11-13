import {useState} from 'react';
import type {Survey,UploadBatch} from '../../types/domain';
import {uploadApi} from '../../api/uploads';

const TEMPLATE=[
 {reference:'SJ-19',name:'林缘补录样线19',habitat:'阔叶林缘',counts:[{species:'S01',count:12},{species:'S02',count:4}]},
 {reference:'SJ-01',name:'林缘样线01',habitat:'阔叶林缘',counts:[{species:'S01',count:15}]}
];

export function BatchSubmitForm({surveys,busy,onClose,onSubmitted}:{surveys:Survey[];busy:boolean;onClose:()=>void;onSubmitted:(b:UploadBatch)=>void}){
 const [surveyId,setSurveyId]=useState(surveys.at(-1)?.id??0);
 const [batchRef,setBatchRef]=useState('FIELD-'+new Date().toISOString().slice(0,10)+'-A');
 const [source,setSource]=useState('field-tablet-');
 const [raw,setRaw]=useState(JSON.stringify(TEMPLATE,null,2));
 const [parseError,setParseError]=useState('');
 const [submitError,setSubmitError]=useState('');
 async function submit(e:React.FormEvent){
  e.preventDefault();setParseError('');setSubmitError('');
  let items:any;
  try{items=JSON.parse(raw);}catch(e){setParseError('JSON无法解析：'+(e as Error).message);return;}
  if(!Array.isArray(items)||!items.length){setParseError('items必须是非空数组，每行一条样线或坏行记录');return;}
  if(!surveyId){setParseError('请先选择调查期');return;}
  try{
   const batch=await uploadApi.submit({batch_ref:batchRef,survey_id:surveyId,source,items});
   onSubmitted(batch);
  }catch(e){setSubmitError((e as Error).message);}
 }
 return <form className="editor upload-form" onSubmit={submit}>
  <h2>整批离线回传</h2>
  <p className="fine">批次号用于野外端重发去重：相同批次号+相同内容重放只累计重发次数、不新增计数；批次号复用但内容不同将被拒绝。每行包含 reference/name/habitat/counts；坏行也整批保留，逐行注明拒收原因。</p>
  <div className="form-grid">
   <label>调查期<select value={surveyId} onChange={e=>setSurveyId(+e.target.value)} required>{surveys.map(s=><option value={s.id} key={s.id}>{s.name} / {s.survey_date}</option>)}</select></label>
   <label>批次号（幂等键）<input value={batchRef} onChange={e=>setBatchRef(e.target.value)} required maxLength={80}/></label>
   <label>来源设备/小组<input value={source} onChange={e=>setSource(e.target.value)} maxLength={120} placeholder="field-tablet-A / 甲组"/></label>
  </div>
  <label>整批JSON（items数组，最多200行）<textarea rows={12} value={raw} onChange={e=>setRaw(e.target.value)} required spellCheck={false} className="mono"/></label>
  {(parseError||submitError)&&<div className="notice error" role="alert">{parseError||submitError}</div>}
  <div className="note-actions"><button type="button" onClick={onClose}>取消</button><button className="primary" disabled={busy}>提交整批回传 →</button></div>
 </form>;
}
