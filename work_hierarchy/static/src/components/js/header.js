/** @odoo-module **/

import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";

export class Header extends MessageBrokerComponent {
    setup() {
        super.setup()
        this.expandAllBomRollup = this.expandAllBomRollup.bind(this);
        this.collapseAllBomRollup = this.collapseAllBomRollup.bind(this);
    }
    
    expandAllBomRollup(){
        this.publish('toggleAll', false);
        $('.o_button_collapse_all_bom_rollup').removeClass('o_hidden');
        $('.o_button_expand_all_bom_rollup').addClass('o_hidden');
    }

    collapseAllBomRollup(){
        this.publish('toggleAll', true);
        $('.o_button_collapse_all_bom_rollup').addClass('o_hidden');
        $('.o_button_expand_all_bom_rollup').removeClass('o_hidden');
    }
}

Header.template = "work_hierarchy.hierarchy_header";
