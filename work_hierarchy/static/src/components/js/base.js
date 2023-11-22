/** @odoo-module **/
import { Component, useSubEnv, useService } from "@odoo/owl";

class MessageBroker {
    constructor() {
        this.subscriptions = {};
    }
    subscribe(eventType, owner, callback) {
        if (!callback) {
            throw new Error("Missing callback");
        }
        if (!this.subscriptions[eventType]) {
            this.subscriptions[eventType] = [];
        }
        this.subscriptions[eventType].push({
            owner,
            callback,
        });
    }
    unsubscribe(eventType, callback) {
        const subs = this.subscriptions[eventType];
        if (subs) {
            this.subscriptions[eventType] = subs.filter((s) => callback != s.callback);
        }
    }
    drop(eventType, owner){
        const subs = this.subscriptions[eventType];
        if (subs) {
            this.subscriptions[eventType] = subs.filter((s) => s.owner !== owner);
        }
    }
    make(owner, args){
        return {
            'timestamp': new Date().getTime(),
            'data': args,
            'source': owner,
            'messageID': (Math.random() + 1).toString(36).substring(7)
        }
    }
    update(owner, args){
        owner['data'] = args
        return owner
    }
    publish(eventType, owner, args, origin=null, patternMode=false) {
        let data = (origin? this.update : this.make)(owner, args)
        let subs = []
        if (patternMode){
            for (const [key, values] of Object.entries(this.subscriptions)) {
                if (key.match(eventType)) subs.push(...values)
            }
        } else{
            subs = this.subscriptions[eventType] || [];
        }
        for (let i = 0, iLen = subs.length; i < iLen; i++) {
            const sub = subs[i];
            if (sub.owner !== owner){
                sub.callback.call(sub.owner, data);
            }
        }
    }
    publishAsync(eventType, owner, args, origin=null, animateDelay=0){
        let base = 0
        let data = (origin? this.update : this.make)(owner, args)
        const subs = this.subscriptions[eventType] || [];
        for (let i = 0, iLen = subs.length; i < iLen; i++) {
            const sub = subs[i];
            if (sub.owner !== owner){
                setTimeout(()=>{
                    sub.callback.call(sub.owner, data);
                }, base)
                base += animateDelay
            }
        }
    }
    clear() {
        this.subscriptions = {};
    }
}

export class serviceStorage{
    constructor(){
        this.storage = {}    
    }

    get(key){
        return this.storage[key]
    }

    set(key, data){
        this.storage[key] = data
        return true
    }
}

var storage = new serviceStorage()

export function getStorage(key){
    return storage.get(key)
}

export function setStorage(key, data){
    return storage.set(key, data)
}

export class MessageBrokerComponent extends Component{
    setup(){ 
        super.setup()
        if (!this.env._bus){
            useSubEnv({
                '_bus': new MessageBroker(),
                'storage': (Math.random() + 1).toString(36).substring(7)
            })
        }
        this.eventLogs = {};
    }
    publish(key, data, patternMode){
        if (this.env._bus){
            this.env._bus.publish(key, this, data, null, patternMode);
        }
    }
    subscribe(key, callback){
        if (this.env._bus){
            this.env._bus.subscribe(key, this, callback);
        }
    }
    unsubscribe(key, callback){
        if (this.env._bus){
            this.env._bus.dropEvent(key, callback);
        }
    }
    forward(key, event, data){
        if (this.env._bus){
            this.env._bus.publish(key, this, data, event);
        }
    }

}
