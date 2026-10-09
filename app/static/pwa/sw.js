/* Network-only: never cache authenticated pages, APIs or household records. */
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(() => new Response('<!doctype html><html lang="da"><meta name="viewport" content="width=device-width"><title>Jarvis er offline</title><h1>Jarvis kan ikke nås</h1><p>Kontrollér forbindelsen til hjemmet. Ingen medicin eller afkrydsninger gemmes offline.</p><button onclick="location.reload()">Prøv igen</button></html>',{status:503,headers:{'Content-Type':'text/html; charset=utf-8'}})));
});
self.addEventListener('push', event => {
  let message={};try{message=event.data?.json()||{};}catch{}
  const url=['/#medicin','/#beskeder'].includes(message.url)?message.url:'/#beskeder';
  event.waitUntil(self.registration.showNotification(String(message.title||'Jarvis').slice(0,100),{
    body:String(message.body||'Du har en påmindelse i Jarvis.').slice(0,500),
    icon:'/static/pwa/icon-192.png',badge:'/static/pwa/icon-192.png',
    tag:String(message.tag||'jarvis').slice(0,100),data:{url}
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const path=['/#medicin','/#beskeder'].includes(event.notification.data?.url)?event.notification.data.url:'/#beskeder';
  const target=new URL(path,self.location.origin).href;
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows){if(new URL(client.url).origin!==self.location.origin)continue;await client.navigate(target);return client.focus();}
    return self.clients.openWindow(target);
  })());
});
