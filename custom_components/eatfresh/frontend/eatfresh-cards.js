function t(t,e,s,i){var r,n=arguments.length,o=n<3?e:null===i?i=Object.getOwnPropertyDescriptor(e,s):i;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)o=Reflect.decorate(t,e,s,i);else for(var a=t.length-1;a>=0;a--)(r=t[a])&&(o=(n<3?r(o):n>3?r(e,s,o):r(e,s))||o);return n>3&&o&&Object.defineProperty(e,s,o),o}"function"==typeof SuppressedError&&SuppressedError;var e="M11,9H9V2H7V9H5V2H3V9C3,11.12 4.66,12.84 6.75,12.97V22H9.25V12.97C11.34,12.84 13,11.12 13,9V2H11V9M16,6V14H18.5V22H21V2C18.24,2 16,4.24 16,6Z";const s=globalThis,i=s.ShadowRoot&&(void 0===s.ShadyCSS||s.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,r=Symbol(),n=new WeakMap;let o=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==r)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const s=void 0!==e&&1===e.length;s&&(t=n.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&n.set(e,t))}return t}toString(){return this.cssText}};const a=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const s of t.cssRules)e+=s.cssText;return(t=>new o("string"==typeof t?t:t+"",void 0,r))(e)})(t):t,{is:h,defineProperty:l,getOwnPropertyDescriptor:d,getOwnPropertyNames:c,getOwnPropertySymbols:p,getPrototypeOf:u}=Object,_=globalThis,f=_.trustedTypes,g=f?f.emptyScript:"",m=_.reactiveElementPolyfillSupport,y=(t,e)=>t,$={toAttribute(t,e){switch(e){case Boolean:t=t?g:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let s=t;switch(e){case Boolean:s=null!==t;break;case Number:s=null===t?null:Number(t);break;case Object:case Array:try{s=JSON.parse(t)}catch(t){s=null}}return s}},v=(t,e)=>!h(t,e),b={attribute:!0,type:String,converter:$,reflect:!1,useDefault:!1,hasChanged:v};Symbol.metadata??=Symbol("metadata"),_.litPropertyMetadata??=new WeakMap;let w=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=b){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const s=Symbol(),i=this.getPropertyDescriptor(t,s,e);void 0!==i&&l(this.prototype,t,i)}}static getPropertyDescriptor(t,e,s){const{get:i,set:r}=d(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:i,set(e){const n=i?.call(this);r?.call(this,e),this.requestUpdate(t,n,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??b}static _$Ei(){if(this.hasOwnProperty(y("elementProperties")))return;const t=u(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(y("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(y("properties"))){const t=this.properties,e=[...c(t),...p(t)];for(const s of e)this.createProperty(s,t[s])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,s]of e)this.elementProperties.set(t,s)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const s=this._$Eu(t,e);void 0!==s&&this._$Eh.set(s,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const s=new Set(t.flat(1/0).reverse());for(const t of s)e.unshift(a(t))}else void 0!==t&&e.push(a(t));return e}static _$Eu(t,e){const s=e.attribute;return!1===s?void 0:"string"==typeof s?s:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,e)=>{if(i)t.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of e){const e=document.createElement("style"),r=s.litNonce;void 0!==r&&e.setAttribute("nonce",r),e.textContent=i.cssText,t.appendChild(e)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){const s=this.constructor.elementProperties.get(t),i=this.constructor._$Eu(t,s);if(void 0!==i&&!0===s.reflect){const r=(void 0!==s.converter?.toAttribute?s.converter:$).toAttribute(e,s.type);this._$Em=t,null==r?this.removeAttribute(i):this.setAttribute(i,r),this._$Em=null}}_$AK(t,e){const s=this.constructor,i=s._$Eh.get(t);if(void 0!==i&&this._$Em!==i){const t=s.getPropertyOptions(i),r="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:$;this._$Em=i;const n=r.fromAttribute(e,t.type);this[i]=n??this._$Ej?.get(i)??n,this._$Em=null}}requestUpdate(t,e,s,i=!1,r){if(void 0!==t){const n=this.constructor;if(!1===i&&(r=this[t]),s??=n.getPropertyOptions(t),!((s.hasChanged??v)(r,e)||s.useDefault&&s.reflect&&r===this._$Ej?.get(t)&&!this.hasAttribute(n._$Eu(t,s))))return;this.C(t,e,s)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:i,wrapped:r},n){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,n??e??this[t]),!0!==r||void 0!==n)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),!0===i&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,s]of t){const{wrapped:t}=s,i=this[e];!0!==t||this._$AL.has(e)||void 0===i||this.C(e,void 0,s,i)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[y("elementProperties")]=new Map,w[y("finalized")]=new Map,m?.({ReactiveElement:w}),(_.reactiveElementVersions??=[]).push("2.1.2");const x=globalThis,A=t=>t,E=x.trustedTypes,k=E?E.createPolicy("lit-html",{createHTML:t=>t}):void 0,S="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,H="?"+C,P=`<${H}>`,O=document,M=()=>O.createComment(""),T=t=>null===t||"object"!=typeof t&&"function"!=typeof t,U=Array.isArray,N="[ \t\n\f\r]",R=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,V=/-->/g,D=/>/g,z=RegExp(`>|${N}(?:([^\\s"'>=/]+)(${N}*=${N}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),j=/'/g,W=/"/g,L=/^(?:script|style|textarea|title)$/i,I=t=>(e,...s)=>({_$litType$:t,strings:e,values:s}),B=I(1),q=I(2),F=Symbol.for("lit-noChange"),K=Symbol.for("lit-nothing"),Z=new WeakMap,G=O.createTreeWalker(O,129);function J(t,e){if(!U(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==k?k.createHTML(e):e}const Y=(t,e)=>{const s=t.length-1,i=[];let r,n=2===e?"<svg>":3===e?"<math>":"",o=R;for(let e=0;e<s;e++){const s=t[e];let a,h,l=-1,d=0;for(;d<s.length&&(o.lastIndex=d,h=o.exec(s),null!==h);)d=o.lastIndex,o===R?"!--"===h[1]?o=V:void 0!==h[1]?o=D:void 0!==h[2]?(L.test(h[2])&&(r=RegExp("</"+h[2],"g")),o=z):void 0!==h[3]&&(o=z):o===z?">"===h[0]?(o=r??R,l=-1):void 0===h[1]?l=-2:(l=o.lastIndex-h[2].length,a=h[1],o=void 0===h[3]?z:'"'===h[3]?W:j):o===W||o===j?o=z:o===V||o===D?o=R:(o=z,r=void 0);const c=o===z&&t[e+1].startsWith("/>")?" ":"";n+=o===R?s+P:l>=0?(i.push(a),s.slice(0,l)+S+s.slice(l)+C+c):s+C+(-2===l?e:c)}return[J(t,n+(t[s]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),i]};class Q{constructor({strings:t,_$litType$:e},s){let i;this.parts=[];let r=0,n=0;const o=t.length-1,a=this.parts,[h,l]=Y(t,e);if(this.el=Q.createElement(h,s),G.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(i=G.nextNode())&&a.length<o;){if(1===i.nodeType){if(i.hasAttributes())for(const t of i.getAttributeNames())if(t.endsWith(S)){const e=l[n++],s=i.getAttribute(t).split(C),o=/([.?@])?(.*)/.exec(e);a.push({type:1,index:r,name:o[2],strings:s,ctor:"."===o[1]?it:"?"===o[1]?rt:"@"===o[1]?nt:st}),i.removeAttribute(t)}else t.startsWith(C)&&(a.push({type:6,index:r}),i.removeAttribute(t));if(L.test(i.tagName)){const t=i.textContent.split(C),e=t.length-1;if(e>0){i.textContent=E?E.emptyScript:"";for(let s=0;s<e;s++)i.append(t[s],M()),G.nextNode(),a.push({type:2,index:++r});i.append(t[e],M())}}}else if(8===i.nodeType)if(i.data===H)a.push({type:2,index:r});else{let t=-1;for(;-1!==(t=i.data.indexOf(C,t+1));)a.push({type:7,index:r}),t+=C.length-1}r++}}static createElement(t,e){const s=O.createElement("template");return s.innerHTML=t,s}}function X(t,e,s=t,i){if(e===F)return e;let r=void 0!==i?s._$Co?.[i]:s._$Cl;const n=T(e)?void 0:e._$litDirective$;return r?.constructor!==n&&(r?._$AO?.(!1),void 0===n?r=void 0:(r=new n(t),r._$AT(t,s,i)),void 0!==i?(s._$Co??=[])[i]=r:s._$Cl=r),void 0!==r&&(e=X(t,r._$AS(t,e.values),r,i)),e}class tt{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:s}=this._$AD,i=(t?.creationScope??O).importNode(e,!0);G.currentNode=i;let r=G.nextNode(),n=0,o=0,a=s[0];for(;void 0!==a;){if(n===a.index){let e;2===a.type?e=new et(r,r.nextSibling,this,t):1===a.type?e=new a.ctor(r,a.name,a.strings,this,t):6===a.type&&(e=new ot(r,this,t)),this._$AV.push(e),a=s[++o]}n!==a?.index&&(r=G.nextNode(),n++)}return G.currentNode=O,i}p(t){let e=0;for(const s of this._$AV)void 0!==s&&(void 0!==s.strings?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}}class et{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,i){this.type=2,this._$AH=K,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=X(this,t,e),T(t)?t===K||null==t||""===t?(this._$AH!==K&&this._$AR(),this._$AH=K):t!==this._$AH&&t!==F&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>U(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==K&&T(this._$AH)?this._$AA.nextSibling.data=t:this.T(O.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:s}=t,i="number"==typeof s?this._$AC(t):(void 0===s.el&&(s.el=Q.createElement(J(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===i)this._$AH.p(e);else{const t=new tt(i,this),s=t.u(this.options);t.p(e),this.T(s),this._$AH=t}}_$AC(t){let e=Z.get(t.strings);return void 0===e&&Z.set(t.strings,e=new Q(t)),e}k(t){U(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let s,i=0;for(const r of t)i===e.length?e.push(s=new et(this.O(M()),this.O(M()),this,this.options)):s=e[i],s._$AI(r),i++;i<e.length&&(this._$AR(s&&s._$AB.nextSibling,i),e.length=i)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=A(t).nextSibling;A(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class st{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,i,r){this.type=1,this._$AH=K,this._$AN=void 0,this.element=t,this.name=e,this._$AM=i,this.options=r,s.length>2||""!==s[0]||""!==s[1]?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=K}_$AI(t,e=this,s,i){const r=this.strings;let n=!1;if(void 0===r)t=X(this,t,e,0),n=!T(t)||t!==this._$AH&&t!==F,n&&(this._$AH=t);else{const i=t;let o,a;for(t=r[0],o=0;o<r.length-1;o++)a=X(this,i[s+o],e,o),a===F&&(a=this._$AH[o]),n||=!T(a)||a!==this._$AH[o],a===K?t=K:t!==K&&(t+=(a??"")+r[o+1]),this._$AH[o]=a}n&&!i&&this.j(t)}j(t){t===K?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class it extends st{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===K?void 0:t}}class rt extends st{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==K)}}class nt extends st{constructor(t,e,s,i,r){super(t,e,s,i,r),this.type=5}_$AI(t,e=this){if((t=X(this,t,e,0)??K)===F)return;const s=this._$AH,i=t===K&&s!==K||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,r=t!==K&&(s===K||i);i&&this.element.removeEventListener(this.name,this,s),r&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class ot{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){X(this,t)}}const at=x.litHtmlPolyfillSupport;at?.(Q,et),(x.litHtmlVersions??=[]).push("3.3.3");const ht=globalThis;class lt extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,s)=>{const i=s?.renderBefore??e;let r=i._$litPart$;if(void 0===r){const t=s?.renderBefore??null;i._$litPart$=r=new et(e.insertBefore(M(),t),t,void 0,s??{})}return r._$AI(t),r})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return F}}lt._$litElement$=!0,lt.finalized=!0,ht.litElementHydrateSupport?.({LitElement:lt});const dt=ht.litElementPolyfillSupport;dt?.({LitElement:lt}),(ht.litElementVersions??=[]).push("4.2.2");const ct={attribute:!0,type:String,converter:$,reflect:!1,hasChanged:v},pt=(t=ct,e,s)=>{const{kind:i,metadata:r}=s;let n=globalThis.litPropertyMetadata.get(r);if(void 0===n&&globalThis.litPropertyMetadata.set(r,n=new Map),"setter"===i&&((t=Object.create(t)).wrapped=!0),n.set(s.name,t),"accessor"===i){const{name:i}=s;return{set(s){const r=e.get.call(this);e.set.call(this,s),this.requestUpdate(i,r,t,!0,s)},init(e){return void 0!==e&&this.C(i,void 0,t,e),e}}}if("setter"===i){const{name:i}=s;return function(s){const r=this[i];e.call(this,s),this.requestUpdate(i,r,t,!0,s)}}throw Error("Unsupported decorator location: "+i)};function ut(t){return function(t){return(e,s)=>"object"==typeof s?pt(t,e,s):((t,e,s)=>{const i=e.hasOwnProperty(s);return e.constructor.createProperty(s,t),i?Object.getOwnPropertyDescriptor(e,s):void 0})(t,e,s)}({...t,state:!0,attribute:!1})}const _t=t=>String(t).padStart(2,"0");function ft(t){return`${t.getFullYear()}-${_t(t.getMonth()+1)}-${_t(t.getDate())}`}function gt(t){const[e,s,i]=t.split("-").map(Number);return new Date(e,(s??1)-1,i??1)}function mt(t,e){const s=gt(t);return s.setDate(s.getDate()+e),ft(s)}function yt(){return ft(new Date)}function $t(t){return mt(t,-(gt(t).getDay()+6)%7)}const vt=t=>"de"===t?"de-DE":"en-GB";const bt={de:{week_title:"Wochenplan",today_title:"Heute gibt es",nothing:"Nichts geplant",nothing_week:"In den nächsten Tagen ist nichts geplant.",plan_now:"Wochenplan öffnen",loading:"Lädt …",error:"Der Wochenplan ließ sich nicht laden.",retry:"Noch mal versuchen",today:"Heute",tomorrow:"Morgen",week_name:"EatFresh: Wochenplan",week_desc:"Die nächsten Tage aus dem Essensplan von KitchenOwl.",today_name:"EatFresh: Heute gibt es",today_desc:"Was heute laut Essensplan auf den Tisch kommt.",bad_days:"„days“ muss eine ganze Zahl von 1 bis 14 sein."},en:{week_title:"Week plan",today_title:"Today’s menu",nothing:"Nothing planned",nothing_week:"Nothing is planned for the next days.",plan_now:"Open week plan",loading:"Loading …",error:"The week plan could not be loaded.",retry:"Try again",today:"Today",tomorrow:"Tomorrow",week_name:"EatFresh: Week plan",week_desc:"The next days from the KitchenOwl meal plan.",today_name:"EatFresh: Today’s menu",today_desc:"What is on the table today according to the meal plan.",bad_days:"“days” must be a whole number from 1 to 14."}},wt=t=>(t??"").toLowerCase().startsWith("de")?"de":"en",xt=()=>wt(document.documentElement.lang||navigator.language),At="/eatfresh",Et=t=>B`<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${q`<path d=${t}></path>`}</svg>`;const kt=((t,...e)=>{const s=1===t.length?t[0]:e.reduce((e,s,i)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[i+1],t[0]);return new o(s,t,r)})`
  :host {
    display: block;
    --efc-primary: var(--primary-color, #03a9f4);
    --efc-on-primary: var(--text-primary-color, #fff);
    --efc-text: var(--primary-text-color, #212121);
    --efc-text2: var(--secondary-text-color, #727272);
    --efc-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --efc-hover: color-mix(in srgb, var(--efc-text) 7%, transparent);
    --efc-tint: color-mix(in srgb, var(--efc-primary) 12%, transparent);
  }
  *, *::before, *::after { box-sizing: border-box; }
  .card {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--efc-text);
    border-radius: var(--ha-card-border-radius, 12px);
    border-width: var(--ha-card-border-width, 1px);
    border-style: solid;
    border-color: var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
    font-family: var(--ha-font-family-body, inherit);
    font-size: var(--ha-font-size-m, 14px);
    line-height: 1.4;
    -webkit-tap-highlight-color: transparent;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 8px 8px 16px;
  }
  .header h2 {
    flex: 1;
    min-width: 0;
    margin: 0;
    color: var(--ha-card-header-color, var(--efc-text));
    font-size: var(--ha-card-header-font-size, var(--ha-font-size-2xl, 24px));
    font-weight: var(--ha-font-weight-normal, 400);
    line-height: 1.33;
    letter-spacing: -0.012em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .header .sub { color: var(--efc-text2); white-space: nowrap; }
  .content { padding: 0 16px 16px; min-width: 0; }
  a { color: inherit; text-decoration: none; }
  .icon-btn {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    color: var(--efc-text2);
  }
  .icon-btn:hover, a.row:hover, a.hero-link:hover { background: var(--efc-hover); }
  :focus-visible { outline: 2px solid var(--efc-primary); outline-offset: 2px; }
  svg.i { width: 24px; height: 24px; fill: currentColor; flex: none; }
  .photo {
    position: relative;
    flex: none;
    display: grid;
    place-items: center;
    overflow: hidden;
    background: color-mix(in srgb, var(--efc-primary) 10%, var(--ha-card-background, var(--card-background-color, #fff)));
    color: color-mix(in srgb, var(--efc-primary) 55%, var(--ha-card-background, var(--card-background-color, #fff)));
  }
  .photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .thumb { width: 40px; height: 40px; border-radius: 8px; }
  .thumb svg.i { width: 20px; height: 20px; }
  .name { min-width: 0; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .muted { color: var(--efc-text2); }
  .note { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 8px 0 4px; text-align: center; color: var(--efc-text2); }
  .note svg.i { width: 32px; height: 32px; opacity: 0.6; }
  .note.error svg.i { color: var(--error-color, #db4437); opacity: 1; }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    padding: 0 16px;
    border: 1px solid var(--efc-divider);
    border-radius: 22px;
    background: transparent;
    color: var(--efc-primary);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .btn:hover { background: var(--efc-tint); }
  .skel { height: 40px; margin: 6px 0; border-radius: 8px; background: var(--efc-hover); animation: pulse 1.4s ease-in-out infinite; }
  .skel.big { height: auto; aspect-ratio: 2 / 1; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) { .skel { animation: none; } }

  /* Week card */
  .days { margin: 0; padding: 0; list-style: none; }
  .day { display: flex; gap: 12px; padding: 6px 0; min-width: 0; }
  .day + .day { border-top: 1px solid var(--efc-divider); }
  .date { flex: none; width: 4.4em; padding-top: 10px; line-height: 1.2; }
  .date .wd { display: block; font-weight: 500; }
  .date .dn { display: block; color: var(--efc-text2); font-size: 0.9em; }
  .day.today .date .wd { color: var(--efc-primary); }
  .meals { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .meals .muted { min-height: 44px; display: flex; align-items: center; }
  a.row { display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 4px 6px; margin: 0 -6px; border-radius: 10px; min-width: 0; }

  /* Today card */
  .hero-link { display: block; margin: 0 -8px; padding: 0 8px 8px; border-radius: 12px; }
  .hero { width: 100%; aspect-ratio: 2 / 1; border-radius: 10px; }
  .hero svg.i { width: 40px; height: 40px; }
  .hero-name { margin-top: 8px; font-size: 1.15em; font-weight: 500; }
  .more a.row { min-height: 52px; }
`;class St extends lt{constructor(){super(...arguments),this._config={},this._lang=xt(),this._weeks=new Map,this._state="loading",this._today=yt(),this._day=yt(),this._seq=0,this._onVisible=()=>{"visible"===document.visibilityState&&this._hass&&this._load()}}static{this.styles=kt}set hass(t){const e=!this._hass&&!!t;this._hass=t;const s=wt(t?.language??t?.locale?.language);s!==this._lang&&(this._lang=s),(e||this._day!==yt())&&this._load()}get hass(){return this._hass}setConfig(t){if(!t||"object"!=typeof t)throw new Error("Invalid configuration");if(null!=t.days&&(!Number.isInteger(t.days)||t.days<1||t.days>14))throw new Error(bt[this._lang].bad_days);this._config={...t},this._hass&&this._load()}connectedCallback(){super.connectedCallback(),this._timer=window.setInterval(()=>this._load(),6e5),document.addEventListener("visibilitychange",this._onVisible),this._hass&&this._load()}disconnectedCallback(){super.disconnectedCallback(),window.clearInterval(this._timer),document.removeEventListener("visibilitychange",this._onVisible)}_t(t){return bt[this._lang][t]}async _load(){if(!this._hass)return;const t=++this._seq;this._day=yt(),this._weeks.size||(this._state="loading");try{const e=await this._hass.callWS({type:"eatfresh/planner"}),s=e.today||yt(),i=await Promise.all(this._neededWeeks(s).filter(t=>t!==e.week_start).map(t=>this._hass.callWS({type:"eatfresh/planner",week_start:t})));if(t!==this._seq)return;this._today=s,this._weeks=new Map([e,...i].map(t=>[t.week_start,t])),this._state="done"}catch{if(t!==this._seq)return;this._state="error"}}_entriesOn(t){const e=this._weeks.get($t(t));return e?.days.find(e=>e.date===t)?.entries??[]}_photo(t,s){return B`<div class="photo ${s}">
      ${Et(e)}
      ${t?B`<img src=${t} alt="" loading="lazy" decoding="async" @error=${t=>t.target.hidden=!0} />`:K}
    </div>`}_link(t,e,s){return B`<a
      class=${s}
      href=${At+t}
      @click=${e=>{e.metaKey||e.ctrlKey||e.shiftKey||0!==e.button||(e.preventDefault(),function(t){window.history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))}(At+t))}}
      >${e}</a
    >`}_recipeRow(t){return this._link(`/collection/${t.kitchenowl_id}`,B`${this._photo(t.image,"thumb")}<span class="name">${t.name}</span>`,"row")}_header(t,e=""){return B`<div class="header">
      <h2>${t}</h2>
      ${e?B`<span class="sub">${e}</span>`:K}
      ${this._link("/planner",Et("M6 1H8V3H16V1H18V3H19C20.11 3 21 3.9 21 5V19C21 20.11 20.11 21 19 21H5C3.89 21 3 20.1 3 19V5C3 3.89 3.89 3 5 3H6V1M5 8V19H19V8H5M7 10H17V12H7V10Z"),"icon-btn")}
    </div>`}_errorNote(){return B`<div class="note error" role="alert">
      ${Et("M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z")}<span>${this._t("error")}</span>
      <button class="btn" @click=${()=>this._load()}>${this._t("retry")}</button>
    </div>`}_emptyNote(t){return B`<div class="note">
      ${Et(e)}<span>${t}</span>
      ${this._link("/planner",B`${this._t("plan_now")}`,"btn")}
    </div>`}}t([ut()],St.prototype,"_config",void 0),t([ut()],St.prototype,"_lang",void 0),t([ut()],St.prototype,"_weeks",void 0),t([ut()],St.prototype,"_state",void 0),t([ut()],St.prototype,"_today",void 0);class Ct extends St{static getStubConfig(){return{days:7}}_daysFrom(t){return Array.from({length:this._config.days??7},(e,s)=>mt(t,s))}get _days(){return this._daysFrom(this._today)}_neededWeeks(t){return[...new Set(this._daysFrom(t).map($t))]}getCardSize(){return 1+Math.ceil(1.1*(this._config.days??7))}getGridOptions(){return{columns:12,min_columns:6}}render(){const t=this._config.title??this._t("week_title"),e=this._days;let s;if("error"!==this._state||this._weeks.size)if("loading"===this._state)s=B`<div aria-busy="true" aria-label=${this._t("loading")}>
        ${e.slice(0,4).map(()=>B`<div class="skel"></div>`)}
      </div>`;else if(e.every(t=>!this._entriesOn(t).length))s=this._emptyNote(this._t("nothing_week"));else{const t=e[0];s=B`<ul class="days">
        ${e.map(e=>{const s=this._entriesOn(e),i=e===t?this._t("today"):e===mt(t,1)?this._t("tomorrow"):function(t,e,s="long"){return gt(e).toLocaleDateString(vt(t),{weekday:s})}(this._lang,e,"short");return B`<li class="day ${e===t?"today":""}">
            <div class="date">
              <span class="wd">${i}</span>
              <span class="dn">${gt(e).getDate()}.${gt(e).getMonth()+1}.</span>
            </div>
            <div class="meals">
              ${s.length?s.map(t=>this._recipeRow(t)):B`<span class="muted">${this._t("nothing")}</span>`}
            </div>
          </li>`})}
      </ul>`}else s=this._errorNote();return B`<div class="card">${this._header(t)}<div class="content">${s}</div></div>`}}class Ht extends St{static getStubConfig(){return{}}_neededWeeks(t){return[$t(t)]}getCardSize(){return 4}getGridOptions(){return{columns:6,min_columns:4}}render(){const t=this._config.title??this._t("today_title"),e=this._today,s=function(t,e,s="long"){return gt(e).toLocaleDateString(vt(t),{weekday:s,day:"numeric",month:"numeric"})}(this._lang,e,"short");let i;if("error"!==this._state||this._weeks.size)if("loading"===this._state)i=B`<div aria-busy="true" aria-label=${this._t("loading")}><div class="skel big"></div><div class="skel"></div></div>`;else{const[t,...s]=this._entriesOn(e);i=t?B`${this._link(`/collection/${t.kitchenowl_id}`,B`${this._photo(t.image,"hero")}<div class="hero-name name">${t.name}</div>`,"hero-link")}
            ${s.length?B`<div class="more">${s.map(t=>this._recipeRow(t))}</div>`:K}`:this._emptyNote(this._t("nothing"))}else i=this._errorNote();return B`<div class="card">${this._header(t,s)}<div class="content">${i}</div></div>`}}customElements.get("eatfresh-week-card")||customElements.define("eatfresh-week-card",Ct),customElements.get("eatfresh-today-card")||customElements.define("eatfresh-today-card",Ht);const Pt=window;Pt.customCards=Pt.customCards??[];const Ot=bt[xt()];for(const t of[{type:"eatfresh-week-card",name:Ot.week_name,description:Ot.week_desc},{type:"eatfresh-today-card",name:Ot.today_name,description:Ot.today_desc}])Pt.customCards.some(e=>e.type===t.type)||Pt.customCards.push({...t,preview:!0});export{Ht as EatFreshTodayCard,Ct as EatFreshWeekCard};
