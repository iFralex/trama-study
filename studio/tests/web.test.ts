import {test} from 'node:test';
import assert from 'node:assert/strict';
import {publicAddress,fetchPublic,clean} from '../server/web';
test('web verification excludes local networks, credentials and executable markup',async()=>{
 for(const ip of ['127.0.0.1','10.0.0.1','172.16.0.1','192.168.1.1','169.254.169.254','::1','::ffff:127.0.0.1','fd00::1'])assert.equal(publicAddress(ip),false,ip);
 assert.equal(publicAddress('8.8.8.8'),true);assert.equal(publicAddress('2606:4700:4700::1111'),true);
 await assert.rejects(()=>fetchPublic('http://localhost/'),/HTTPS/);
 await assert.rejects(()=>fetchPublic('https://user:password@example.com/'),/HTTPS/);
 await assert.rejects(()=>fetchPublic('https://127.0.0.1/'),/pubblico/);
 assert.equal(clean('<script>bad()</script><p>Primary &amp; verified</p>'),'Primary & verified');
});
