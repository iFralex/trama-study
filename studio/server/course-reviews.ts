import {fsrs,createEmptyCard,Rating} from 'ts-fsrs';
import {Bridge} from './bridge';
/** Scheduling is not a mastery certificate: generated grades remain provisional. */
export async function scheduleCourseRecall(bridge:Bridge,sid:string,attemptId:string){
  const info=await bridge.call('course_recall_card',{sid,attempt_id:attemptId});
  if(!info||info.duplicate||info.correct===null)return;
  const card=info.card??createEmptyCard();
  for(const key of ['due','last_review'])if(card[key])card[key]=new Date(card[key]);
  const rating=info.correct?(info.aids?Rating.Hard:Rating.Good):Rating.Again;
  const scheduled=fsrs().next(card,new Date(),rating);
  await bridge.call('course_recall_card',{sid,attempt_id:attemptId,card:scheduled.card});
}
