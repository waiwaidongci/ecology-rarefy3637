import {request,post} from './client';import type {UploadBatch} from '../types/domain';
export const uploadApi={
 batches:()=>request<UploadBatch[]>('/uploads'),
 batch:(id:number)=>request<UploadBatch>('/uploads/'+id),
 submit:(data:any)=>post('/uploads',data),
 resolve:(itemId:number,decision:'overwrite'|'keep',note:string)=>request('/upload-items/'+itemId+'/resolution',{method:'POST',body:JSON.stringify({decision,note})})
};
