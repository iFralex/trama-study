/** Bounded foreground windows; sleep, wall-clock changes and background gaps stay separate. */
export class StudyClock {
 private lastMono:number;private lastWall:number;private active=false;
 private start:number|null=null;private end=0;private seconds=0;
 private completed:{started:number,ended:number,seconds:number}[]=[];
 constructor(mono:number,wall:number){this.lastMono=mono;this.lastWall=wall;}
 private extract(){
  const value=this.start!==null&&this.end>this.start?{started:this.start,ended:this.end,seconds:Math.min(this.seconds,(this.end-this.start)/1000)}:null;
  this.start=null;this.seconds=0;return value;
 }
 advance(mono:number,wall:number,eligible:boolean){
  const delta=(mono-this.lastMono)/1000,wallDelta=(wall-this.lastWall)/1000;
  if(delta>15||delta<0||Math.abs(wallDelta-delta)>=2){const old=this.extract();if(old)this.completed.push(old);}
  else if(this.active&&delta>0){if(this.start===null)this.start=this.lastWall;this.end=wall;this.seconds+=delta;}
  if(!eligible){const old=this.extract();if(old)this.completed.push(old);}
  this.lastMono=mono;this.lastWall=wall;this.active=eligible;
 }
 take(){return this.completed.shift()??this.extract();}
}
