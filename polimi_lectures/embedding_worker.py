"""Persistent local ONNX embedding worker; no access to the study database."""
import argparse
import contextlib
import hashlib
import json
import os
import sys

MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--cache',required=True);args=parser.parse_args()
    os.environ['HF_HOME']=args.cache
    os.environ['HF_HUB_DISABLE_XET']='1'
    with contextlib.redirect_stdout(sys.stderr):
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer
        model=TextEmbedding(MODEL,cache_dir=args.cache,threads=2)
        tokenizer=Tokenizer.from_str(model.model.tokenizer.to_str())
        tokenizer.no_truncation();tokenizer.no_padding()
        model_file=model.model._model_dir/model.model.model_description.model_file
        digest=hashlib.sha256()
        with model_file.open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
        identity=MODEL+'@'+digest.hexdigest()[:16]+'-tokens120-stride96-v1'
    for line in sys.stdin:
        request={}
        try:
            request=json.loads(line);payload=request['args'];result=None
            if request['method']=='info':result={'model':identity,'dimensions':384}
            elif request['method']=='query':
                result=list(model.embed([str(payload['query'])[:4000]]))[0].tolist()
            elif request['method']=='documents':
                items=payload['items'];texts=[];counts=[]
                for item in items:
                    text=item['text'];tokens=tokenizer.encode(text,add_special_tokens=False)
                    chunks=[]
                    for start in range(0,len(tokens.ids),96):
                        stop=min(start+120,len(tokens.ids));left=tokens.offsets[start][0];right=tokens.offsets[stop-1][1]
                        chunks.append(text[left:right])
                        if stop==len(tokens.ids):break
                    chunks=chunks or [' '];counts.append(len(chunks));texts.extend(chunks)
                with contextlib.redirect_stdout(sys.stderr):vectors=[v.tolist() for v in model.embed(texts,batch_size=32)]
                result=[];offset=0
                for item,count in zip(items,counts):
                    result.append({'id':item['id'],'fingerprint':item['fingerprint'],'vectors':vectors[offset:offset+count]});offset+=count
            else:raise ValueError('Metodo embeddings non disponibile.')
            print(json.dumps({'id':request['id'],'result':result}),flush=True)
        except Exception as exc:print(json.dumps({'id':request.get('id'),'error':str(exc)[:500]}),flush=True)
if __name__=='__main__':main()
