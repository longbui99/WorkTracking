/** @odoo-module **/
import { useRef, onMounted, onPatched, onWillPatch } from "@odoo/owl"
import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";
import { formatFloat } from "@web/core/utils/numbers";
import { useService } from "@web/core/utils/hooks";
import { getStorage } from "@work_hierarchy/components/js/base";
import { App} from "@odoo/owl";
import { templates } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";


export class Line extends MessageBrokerComponent {

    // --------------------------- LINE MESSAGE CONSTRUCTOR --------------------
    static get_margin_unit(){
        return 20
    }

    __setupData(){
        this.animateDelay = 300;
        this.childrens = [];
        this.foldable=false;
        this.fold=false;
        
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.key = this.props.key;
        this.isRoot = this.props.root || false;
        this.margin = this.props.level * Line.get_margin_unit();
        this.parent = this.props.parent;

        let payload = getStorage(this.env.storage);
        this.headers = payload.headers;
        this.recordData = payload.datas[this.key];
        this.currency = this.env.currency;
        if (this.recordData.children_nodes.length){
            this.recordData.name += ` (${this.recordData.children_nodes.length})`
        }

        this.toggleFoldState = this.toggleFoldState.bind(this);
        this.lineComponent = useRef("lineComponent"),
        onPatched(() => {
            for (let child of this.childrens) {
                child.__owl__.destroy();
            }
            this.__renderChildrenNodes()
        });
    }

    onPatched(){
    }
    __setupDOM(){
        this.childLineTemplate = Line;
    }

    __setupLifeCycle(){
        onMounted(()=>{
            this.mounted();
        })
    }


    setup() {
        super.setup()
        this.__setupData();
        this.__setupLifeCycle();
        this.__setupDOM();
        // this.__setupDOM();
    }
    // ----------------------------- DOM EVENT, UI/UX INTERACTION ----------------------------
    convertNumToTime(float) {
        var sign = (float >= 0) ? 1 : -1;
        float = float * sign;
        var hour = Math.floor(float);
        var decpart = float - hour;
        var min = 1 / 60;
        decpart = min * Math.round(decpart / min);
        var minute = Math.floor(decpart * 60) + '';
        if (minute.length < 2) {
            minute = '0' + minute; 
        }
        sign = sign == 1 ? '' : '-';
        return sign + hour + ':' + minute;
    }
    
    elementChangeAnimation(element){
        if (element.classList.contains('element-update')){
            let self = this;
            setTimeout(()=>self.elementChangeAnimation(element), 50)
        } else {
            element.classList.add('element-update');
            setTimeout(()=>{
                element.classList.remove('element-update')
            }, this.animateDelay)
        }
    }

    convertInputCurrencyToNumeric(value){
        if (this.currency?.symbol){
            value = (value || '').replaceAll(this.currency.symbol, '').replaceAll(',', '').trim();
            if (!value.length){
                value = 0;
            } 
            return value
        }
        return value
    }

    updateDOMNumber(element, value){
        if (element.tagName.toLowerCase() === "input"){
            element.value = this.getFormattedCost(value);
        } else {
            element.textContent = this.getFormattedCost(value);
        }
    }
    
    saveInputCurrencyBeforeAnonymize(event){
        if (event?.target){
            event.target.activeValue = event.target.value;
        }
    }

    anonymizeInputCurrency(event){
        if (event?.target && this.currency?.symbol){
            let value = event.target.value;
            let stripValue = (value || '').trim().replaceAll(',', '');
            let isHavingSymbol = stripValue.includes(this.currency.symbol);
            let numberValue = parseFloat(stripValue.replaceAll(this.currency.symbol, ''))
            if (!Number.isFinite(numberValue) && !isHavingSymbol){
                event.stopPropagation();
                event.target.value = event.target.activeValue;
            }
        }
    }

    // ----------------------------- GENERAL PROCESS -----------------------------------------

    getFormattedSymbol(cost){
        if (this.currency.position === "after") {
            return `${cost} ${this.currency.symbol}`;
        } else {
            return `${this.currency.symbol} ${cost}`;
        }     
    }
    
    getFormattedCost(cost){
        let formattedValue = formatFloat(cost, {digits: this.currency.digits });
        return this.getFormattedSymbol(formattedValue)
    }
    
    getFormattedNumber(cost){
        return parseFloat(cost).toFixed(this.currency.digits[1] || 2)
    }

    getFormattedFloat(cost){
        return parseFloat(this.getFormattedNumber(cost))
    }


    _subscribeDataChange(){
        this.subscribe(this.key, this.updateValues.bind(this));
        if (this.props.level == 0){
            this.subscribe("toggleAll", this.forceLineState.bind(this));
        }
    }

    async __renderChildrenNodes(){
        if (this.parent?.nodeDOM){
            this.nodeDOM = this.parent.nodeDOM;
        } else {
            this.nodeDOM = this.lineComponent.el.parentNode;
        }
        this.group = (Math.random() + 1).toString(36).substring(10);
        if (this.recordData.children_nodes.length){
            this.foldable = true;
            this.__setFoldableState();
        }
        this.childrens = []
        for (let child of this.recordData.children_nodes){
            let props = {
                'key': child,
                'level': this.props.level + 1,
                'root': false,
                'parent': this,
                'group': this.group
            }
            let line = new App(this.childLineTemplate, {
                name: child,
                env: this.env,
                dev: this.env.debug,
                templates,
                props,
                translatableAttributes: ["data-tooltip"],
                translateFn: _t,
            })
            await line.mount(this.nodeDOM)
            let subLineComponent = line.root.component
            this.childrens.push(subLineComponent)
            this.nodeDOM.insertBefore(subLineComponent.lineComponent.el, this.lineComponent.el.nextSibling)
        }
    }

    __initEvent(){
        this._subscribeDataChange();
    }

    __setFoldableState(){
        if (this.foldable){
            this.lineComponent.el.classList.add('foldable')
        } else{
            this.lineComponent.el.classList.remove('foldable')
        }
    }
    __setFoldState(fold){
        if (fold){
            this.lineComponent.el.classList.add('d-none')
        } else {
            this.lineComponent.el.classList.remove('d-none')
        }
    }

    actionToggleDisplay(fold){
        this.__setFoldState(fold);
        if (fold || !this.fold){
            this.recursiveToggleDisplay(fold);  
        }
    }

    recursiveToggleDisplay(fold){
        for (let child of this.childrens){
            child.actionToggleDisplay(fold);
        }
    }

    _setFoldMark(){
        if (!this.fold){
            this.lineComponent.el.classList.remove('fold')
        } else{
            this.lineComponent.el.classList.add('fold')
        }
    }

    actionOpenRecord(event) {
        event.stopPropagation();
    }

    toggleFoldState(event){
        this.fold = !this.fold;
        this._setFoldMark();
        this.recursiveToggleDisplay(this.fold)
    }

    onLineClick(event){
        if (this.foldable){
            this.toggleFoldState(event);
        } else {
            this.actionOpenRecord(event);   
        }
    }

    updateFoldForceState(state){
        this.fold = state;
        this._setFoldMark();
        this.__setFoldState(state);
        this.recursiveForceState(state);
    }

    recursiveForceState(state){
        for (let child of this.childrens){
            child.updateFoldForceState(state);
        }
    }

    forceLineState(state){
        if (this.lineComponent.el) {
            this.fold = state.data;
            this._setFoldMark();
            this.recursiveForceState(state.data)
        }
    }

    // -------------------------------- MESSAGE PRODUCE LOGICS ---------------------------
    
    updateLineState(){
        
    }

    // ------------------------------------- MESSAGE CONSUME LOGICS ------------------------

    _isProcessedEvent(event){
        let isProcessed = true
        if (this.lastMessageID !== event.messageID)
            this.lastMessage = event.messageID;
            isProcessed = false
        return isProcessed
    }
    
    _gatherProcessedID(event){
        this.lastMessage = event.messageID;
    }

    updateValues(body){
        if (this._isProcessedEvent(body)) return false;
        return true
    }

    mounted(){
        this.__renderChildrenNodes();
        // this.__initEvent();
    }
}

Line.template = "work_hierarchy.work_hierarchy_line";
