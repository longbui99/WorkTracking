/** @odoo-module **/
import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";
import { formatFloat } from "@web/core/utils/numbers";
import { useService } from "@web/core/utils/hooks";


export class Line extends MessageBrokerComponent {

    // --------------------------- LINE MESSAGE CONSTRUCTOR --------------------
    static get_margin_unit(){
        return 20
    }

    __setupData(){
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.key = this.props.key;
        this.isRoot = this.props.root || false;
        this.margin = this.props.level * Line.get_margin_unit();
        this.animateDelay = 300;
        this.foldable=false;
        this.fold=false;
        this.toggleFoldState = this.toggleFoldState.bind(this);
        this.childrens = []
    }

    __setupDOM(){
        this.childLineTemplate = Line;
        this.saveInputCurrencyBeforeAnonymize = this.saveInputCurrencyBeforeAnonymize.bind(this);
        this.anonymizeInputCurrency = this.anonymizeInputCurrency.bind(this);
    }

    __setupState(){
        this.data = this.env.data;
        this.lineData = this.data[this.key];
        this.currency = this.env.currency;
        this.isManager = this.env.isManager;
        if(!this.env.rootNode){
            this.env.rootNode = this;
        }
    }


    setup() {
        super.setup()
        this.__setupData();
        this.__setupState();
        this.__setupDOM();
    }
    // ----------------------------- DOM EVENT, UI/UX INTERACTION ----------------------------

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
        let node = this.el;
        if (this.env.rootNode){
            node = this.env.rootNode.el.parentNode;
        }
        this.group = (Math.random() + 1).toString(36).substring(10);
        if (this.data[this.key].children_nodes.length){
            this.foldable = true;
            this.__setFoldableState();
        }
        for (let child of this.data[this.key].children_nodes){
            let line = new this.childLineTemplate(this, {
                'key': child,
                'level': this.props.level + 1,
                'root': false,
                'parent': this,
                'group': this.group
            })
            await line.mount(node)
            this.childrens.push(line)
            this.el.parentNode.insertBefore(line.el, this.el.nextSibling)
        }
    }

    __initEvent(){
        this._subscribeDataChange();
    }

    __setFoldableState(){
        if (this.foldable){
            this.el.classList.add('foldable')
        } else{
            this.el.classList.remove('foldable')
        }
    }
    __setFoldState(fold){
        if (fold){
            this.el.classList.add('d-none')
        } else {
            this.el.classList.remove('d-none')
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
            this.el.classList.remove('fold')
        } else{
            this.el.classList.add('fold')
        }
    }

    toggleFoldState(){
        this.fold = !this.fold;
        this._setFoldMark();
        this.recursiveToggleDisplay(this.fold)
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
        if (this.el) {
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

    actionOpenRecord() {
    }

    mounted(){
        super.mounted();
        this.__renderChildrenNodes();
        this.__initEvent();
    }
}

Line.template = "work_hierarchy.work_hierarchy_line";
