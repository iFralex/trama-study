import type {Bridge} from './bridge';

/** Identity belongs to the installation, never to a browser tab or login attempt. */
export async function installationLoginOptions(bridge:Bridge){
  const deviceId=await bridge.call('installation_id');
  return {getDeviceId:()=>deviceId,agentName:'Polimi Studio'};
}
