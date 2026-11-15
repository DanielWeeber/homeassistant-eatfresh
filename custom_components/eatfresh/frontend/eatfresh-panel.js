function e(e,t,i,s){var r,n=arguments.length,o=n<3?t:null===s?s=Object.getOwnPropertyDescriptor(t,i):s;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)o=Reflect.decorate(e,t,i,s);else for(var a=e.length-1;a>=0;a--)(r=e[a])&&(o=(n<3?r(o):n>3?r(t,i,o):r(t,i))||o);return n>3&&o&&Object.defineProperty(t,i,o),o}"function"==typeof SuppressedError&&SuppressedError;var t="M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z",i="M11 9H13V6H16V4H13V1H11V4H8V6H11M7 18C5.9 18 5 18.9 5 20S5.9 22 7 22 9 21.1 9 20 8.1 18 7 18M17 18C15.9 18 15 18.9 15 20S15.9 22 17 22 19 21.1 19 20 18.1 18 17 18M7.2 14.8V14.7L8.1 13H15.5C16.2 13 16.9 12.6 17.2 12L21.1 5L19.4 4L15.5 11H8.5L4.3 2H1V4H3L6.6 11.6L5.2 14C5.1 14.3 5 14.6 5 15C5 16.1 5.9 17 7 17H19V15H7.4C7.3 15 7.2 14.9 7.2 14.8Z",s="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z",r="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z",n="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",o="M12.1,18.55L12,18.65L11.89,18.55C7.14,14.24 4,11.39 4,8.5C4,6.5 5.5,5 7.5,5C9.04,5 10.54,6 11.07,7.36H12.93C13.46,6 14.96,5 16.5,5C18.5,5 20,6.5 20,8.5C20,11.39 16.86,14.24 12.1,18.55M16.5,3C14.76,3 13.09,3.81 12,5.08C10.91,3.81 9.24,3 7.5,3C4.42,3 2,5.41 2,8.5C2,12.27 5.4,15.36 10.55,20.03L12,21.35L13.45,20.03C18.6,15.36 22,12.27 22,8.5C22,5.41 19.58,3 16.5,3Z",a="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z",l="M14,3V5H17.59L7.76,14.83L9.17,16.24L19,6.41V10H21V3M19,19H5V5H12V3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19Z",c="M11,9H9V2H7V9H5V2H3V9C3,11.12 4.66,12.84 6.75,12.97V22H9.25V12.97C11.34,12.84 13,11.12 13,9V2H11V9M16,6V14H18.5V22H21V2C18.24,2 16,4.24 16,6Z";const h=globalThis,p=h.ShadowRoot&&(void 0===h.ShadyCSS||h.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,d=Symbol(),u=new WeakMap;let _=class{constructor(e,t,i){if(this._$cssResult$=!0,i!==d)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(p&&void 0===e){const i=void 0!==t&&1===t.length;i&&(e=u.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),i&&u.set(t,e))}return e}toString(){return this.cssText}};const f=p?e=>e:e=>e instanceof CSSStyleSheet?(e=>{let t="";for(const i of e.cssRules)t+=i.cssText;return(e=>new _("string"==typeof e?e:e+"",void 0,d))(t)})(e):e,{is:g,defineProperty:v,getOwnPropertyDescriptor:m,getOwnPropertyNames:b,getOwnPropertySymbols:y,getPrototypeOf:$}=Object,x=globalThis,w=x.trustedTypes,k=w?w.emptyScript:"",S=x.reactiveElementPolyfillSupport,A=(e,t)=>e,C={toAttribute(e,t){switch(t){case Boolean:e=e?k:null;break;case Object:case Array:e=null==e?e:JSON.stringify(e)}return e},fromAttribute(e,t){let i=e;switch(t){case Boolean:i=null!==e;break;case Number:i=null===e?null:Number(e);break;case Object:case Array:try{i=JSON.parse(e)}catch(e){i=null}}return i}},E=(e,t)=>!g(e,t),L={attribute:!0,type:String,converter:C,reflect:!1,useDefault:!1,hasChanged:E};Symbol.metadata??=Symbol("metadata"),x.litPropertyMetadata??=new WeakMap;let M=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=L){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){const i=Symbol(),s=this.getPropertyDescriptor(e,i,t);void 0!==s&&v(this.prototype,e,s)}}static getPropertyDescriptor(e,t,i){const{get:s,set:r}=m(this.prototype,e)??{get(){return this[t]},set(e){this[t]=e}};return{get:s,set(t){const n=s?.call(this);r?.call(this,t),this.requestUpdate(e,n,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??L}static _$Ei(){if(this.hasOwnProperty(A("elementProperties")))return;const e=$(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(A("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(A("properties"))){const e=this.properties,t=[...b(e),...y(e)];for(const i of t)this.createProperty(i,e[i])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[e,i]of t)this.elementProperties.set(e,i)}this._$Eh=new Map;for(const[e,t]of this.elementProperties){const i=this._$Eu(e,t);void 0!==i&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const i=new Set(e.flat(1/0).reverse());for(const e of i)t.unshift(f(e))}else void 0!==e&&t.push(f(e));return t}static _$Eu(e,t){const i=t.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const i of t.keys())this.hasOwnProperty(i)&&(e.set(i,this[i]),delete this[i]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((e,t)=>{if(p)e.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const i of t){const t=document.createElement("style"),s=h.litNonce;void 0!==s&&t.setAttribute("nonce",s),t.textContent=i.cssText,e.appendChild(t)}})(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,i){this._$AK(e,i)}_$ET(e,t){const i=this.constructor.elementProperties.get(e),s=this.constructor._$Eu(e,i);if(void 0!==s&&!0===i.reflect){const r=(void 0!==i.converter?.toAttribute?i.converter:C).toAttribute(t,i.type);this._$Em=e,null==r?this.removeAttribute(s):this.setAttribute(s,r),this._$Em=null}}_$AK(e,t){const i=this.constructor,s=i._$Eh.get(e);if(void 0!==s&&this._$Em!==s){const e=i.getPropertyOptions(s),r="function"==typeof e.converter?{fromAttribute:e.converter}:void 0!==e.converter?.fromAttribute?e.converter:C;this._$Em=s;const n=r.fromAttribute(t,e.type);this[s]=n??this._$Ej?.get(s)??n,this._$Em=null}}requestUpdate(e,t,i,s=!1,r){if(void 0!==e){const n=this.constructor;if(!1===s&&(r=this[e]),i??=n.getPropertyOptions(e),!((i.hasChanged??E)(r,t)||i.useDefault&&i.reflect&&r===this._$Ej?.get(e)&&!this.hasAttribute(n._$Eu(e,i))))return;this.C(e,t,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:i,reflect:s,wrapped:r},n){i&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,n??t??this[e]),!0!==r||void 0!==n)||(this._$AL.has(e)||(this.hasUpdated||i||(t=void 0),this._$AL.set(e,t)),!0===s&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[e,t]of this._$Ep)this[e]=t;this._$Ep=void 0}const e=this.constructor.elementProperties;if(e.size>0)for(const[t,i]of e){const{wrapped:e}=i,s=this[t];!0!==e||this._$AL.has(t)||void 0===s||this.C(t,void 0,i,s)}}let e=!1;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(t){throw e=!1,this._$EM(),t}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(e){}firstUpdated(e){}};M.elementStyles=[],M.shadowRootOptions={mode:"open"},M[A("elementProperties")]=new Map,M[A("finalized")]=new Map,S?.({ReactiveElement:M}),(x.reactiveElementVersions??=[]).push("2.1.2");const H=globalThis,T=e=>e,R=H.trustedTypes,z=R?R.createPolicy("lit-html",{createHTML:e=>e}):void 0,P="$lit$",V=`lit$${Math.random().toFixed(9).slice(2)}$`,O="?"+V,U=`<${O}>`,N=document,B=()=>N.createComment(""),D=e=>null===e||"object"!=typeof e&&"function"!=typeof e,j=Array.isArray,I="[ \t\n\f\r]",q=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Z=/-->/g,F=/>/g,K=RegExp(`>|${I}(?:([^\\s"'>=/]+)(${I}*=${I}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),W=/'/g,Q=/"/g,G=/^(?:script|style|textarea|title)$/i,J=e=>(t,...i)=>({_$litType$:e,strings:t,values:i}),X=J(1),Y=J(2),ee=Symbol.for("lit-noChange"),te=Symbol.for("lit-nothing"),ie=new WeakMap,se=N.createTreeWalker(N,129);function re(e,t){if(!j(e)||!e.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==z?z.createHTML(t):t}const ne=(e,t)=>{const i=e.length-1,s=[];let r,n=2===t?"<svg>":3===t?"<math>":"",o=q;for(let t=0;t<i;t++){const i=e[t];let a,l,c=-1,h=0;for(;h<i.length&&(o.lastIndex=h,l=o.exec(i),null!==l);)h=o.lastIndex,o===q?"!--"===l[1]?o=Z:void 0!==l[1]?o=F:void 0!==l[2]?(G.test(l[2])&&(r=RegExp("</"+l[2],"g")),o=K):void 0!==l[3]&&(o=K):o===K?">"===l[0]?(o=r??q,c=-1):void 0===l[1]?c=-2:(c=o.lastIndex-l[2].length,a=l[1],o=void 0===l[3]?K:'"'===l[3]?Q:W):o===Q||o===W?o=K:o===Z||o===F?o=q:(o=K,r=void 0);const p=o===K&&e[t+1].startsWith("/>")?" ":"";n+=o===q?i+U:c>=0?(s.push(a),i.slice(0,c)+P+i.slice(c)+V+p):i+V+(-2===c?t:p)}return[re(e,n+(e[i]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),s]};class oe{constructor({strings:e,_$litType$:t},i){let s;this.parts=[];let r=0,n=0;const o=e.length-1,a=this.parts,[l,c]=ne(e,t);if(this.el=oe.createElement(l,i),se.currentNode=this.el.content,2===t||3===t){const e=this.el.content.firstChild;e.replaceWith(...e.childNodes)}for(;null!==(s=se.nextNode())&&a.length<o;){if(1===s.nodeType){if(s.hasAttributes())for(const e of s.getAttributeNames())if(e.endsWith(P)){const t=c[n++],i=s.getAttribute(e).split(V),o=/([.?@])?(.*)/.exec(t);a.push({type:1,index:r,name:o[2],strings:i,ctor:"."===o[1]?pe:"?"===o[1]?de:"@"===o[1]?ue:he}),s.removeAttribute(e)}else e.startsWith(V)&&(a.push({type:6,index:r}),s.removeAttribute(e));if(G.test(s.tagName)){const e=s.textContent.split(V),t=e.length-1;if(t>0){s.textContent=R?R.emptyScript:"";for(let i=0;i<t;i++)s.append(e[i],B()),se.nextNode(),a.push({type:2,index:++r});s.append(e[t],B())}}}else if(8===s.nodeType)if(s.data===O)a.push({type:2,index:r});else{let e=-1;for(;-1!==(e=s.data.indexOf(V,e+1));)a.push({type:7,index:r}),e+=V.length-1}r++}}static createElement(e,t){const i=N.createElement("template");return i.innerHTML=e,i}}function ae(e,t,i=e,s){if(t===ee)return t;let r=void 0!==s?i._$Co?.[s]:i._$Cl;const n=D(t)?void 0:t._$litDirective$;return r?.constructor!==n&&(r?._$AO?.(!1),void 0===n?r=void 0:(r=new n(e),r._$AT(e,i,s)),void 0!==s?(i._$Co??=[])[s]=r:i._$Cl=r),void 0!==r&&(t=ae(e,r._$AS(e,t.values),r,s)),t}class le{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:i}=this._$AD,s=(e?.creationScope??N).importNode(t,!0);se.currentNode=s;let r=se.nextNode(),n=0,o=0,a=i[0];for(;void 0!==a;){if(n===a.index){let t;2===a.type?t=new ce(r,r.nextSibling,this,e):1===a.type?t=new a.ctor(r,a.name,a.strings,this,e):6===a.type&&(t=new _e(r,this,e)),this._$AV.push(t),a=i[++o]}n!==a?.index&&(r=se.nextNode(),n++)}return se.currentNode=N,s}p(e){let t=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(e,i,t),t+=i.strings.length-2):i._$AI(e[t])),t++}}class ce{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,i,s){this.type=2,this._$AH=te,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=ae(this,e,t),D(e)?e===te||null==e||""===e?(this._$AH!==te&&this._$AR(),this._$AH=te):e!==this._$AH&&e!==ee&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):(e=>j(e)||"function"==typeof e?.[Symbol.iterator])(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==te&&D(this._$AH)?this._$AA.nextSibling.data=e:this.T(N.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:i}=e,s="number"==typeof i?this._$AC(e):(void 0===i.el&&(i.el=oe.createElement(re(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(t);else{const e=new le(s,this),i=e.u(this.options);e.p(t),this.T(i),this._$AH=e}}_$AC(e){let t=ie.get(e.strings);return void 0===t&&ie.set(e.strings,t=new oe(e)),t}k(e){j(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let i,s=0;for(const r of e)s===t.length?t.push(i=new ce(this.O(B()),this.O(B()),this,this.options)):i=t[s],i._$AI(r),s++;s<t.length&&(this._$AR(i&&i._$AB.nextSibling,s),t.length=s)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){const t=T(e).nextSibling;T(e).remove(),e=t}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}}class he{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,i,s,r){this.type=1,this._$AH=te,this._$AN=void 0,this.element=e,this.name=t,this._$AM=s,this.options=r,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=te}_$AI(e,t=this,i,s){const r=this.strings;let n=!1;if(void 0===r)e=ae(this,e,t,0),n=!D(e)||e!==this._$AH&&e!==ee,n&&(this._$AH=e);else{const s=e;let o,a;for(e=r[0],o=0;o<r.length-1;o++)a=ae(this,s[i+o],t,o),a===ee&&(a=this._$AH[o]),n||=!D(a)||a!==this._$AH[o],a===te?e=te:e!==te&&(e+=(a??"")+r[o+1]),this._$AH[o]=a}n&&!s&&this.j(e)}j(e){e===te?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}}class pe extends he{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===te?void 0:e}}class de extends he{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==te)}}class ue extends he{constructor(e,t,i,s,r){super(e,t,i,s,r),this.type=5}_$AI(e,t=this){if((e=ae(this,e,t,0)??te)===ee)return;const i=this._$AH,s=e===te&&i!==te||e.capture!==i.capture||e.once!==i.once||e.passive!==i.passive,r=e!==te&&(i===te||s);s&&this.element.removeEventListener(this.name,this,i),r&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}}class _e{constructor(e,t,i){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(e){ae(this,e)}}const fe=H.litHtmlPolyfillSupport;fe?.(oe,ce),(H.litHtmlVersions??=[]).push("3.3.3");const ge=globalThis;class ve extends M{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=((e,t,i)=>{const s=i?.renderBefore??t;let r=s._$litPart$;if(void 0===r){const e=i?.renderBefore??null;s._$litPart$=r=new ce(t.insertBefore(B(),e),e,void 0,i??{})}return r._$AI(e),r})(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return ee}}ve._$litElement$=!0,ve.finalized=!0,ge.litElementHydrateSupport?.({LitElement:ve});const me=ge.litElementPolyfillSupport;me?.({LitElement:ve}),(ge.litElementVersions??=[]).push("4.2.2");const be={attribute:!0,type:String,converter:C,reflect:!1,hasChanged:E},ye=(e=be,t,i)=>{const{kind:s,metadata:r}=i;let n=globalThis.litPropertyMetadata.get(r);if(void 0===n&&globalThis.litPropertyMetadata.set(r,n=new Map),"setter"===s&&((e=Object.create(e)).wrapped=!0),n.set(i.name,e),"accessor"===s){const{name:s}=i;return{set(i){const r=t.get.call(this);t.set.call(this,i),this.requestUpdate(s,r,e,!0,i)},init(t){return void 0!==t&&this.C(s,void 0,e,t),t}}}if("setter"===s){const{name:s}=i;return function(i){const r=this[s];t.call(this,i),this.requestUpdate(s,r,e,!0,i)}}throw Error("Unsupported decorator location: "+s)};function $e(e){return(t,i)=>"object"==typeof i?ye(e,t,i):((e,t,i)=>{const s=t.hasOwnProperty(i);return t.constructor.createProperty(i,e),s?Object.getOwnPropertyDescriptor(t,i):void 0})(e,t,i)}function xe(e){return $e({...e,state:!0,attribute:!1})}const we={title:"EatFresh",menu:"Menü",nav_search:"Suche",nav_collection:"Sammlung",nav_label:"Ansichten",search_label:"Rezepte suchen",search_placeholder:"Was möchtest du kochen?",search_button:"Suchen",sources_label:"Quellen",link_title:"Rezept-Link einfügen",link_placeholder:"https://…",link_button:"Öffnen",link_hint:"Link zu einem Rezept von einer beliebigen Seite.",link_invalid:"Das ist kein gültiger Link. Er muss mit „https://“ beginnen.",search_start:"Gib oben ein, worauf du Lust hast, z. B. „Kürbissuppe“.",search_empty:"Keine Rezepte gefunden. Versuch es mit einem anderen Wort.",search_no_sources:"Wähle mindestens eine Quelle aus.",source_failed:"„{source}“ hat nicht geantwortet: {message}",loading:"Lädt …",retry:"Noch mal versuchen",back:"Zurück",favorite_add:"Merken",favorite_remove:"Nicht mehr merken",favorite_failed:"Merken hat nicht geklappt: {message}",unfavorite_failed:"Entfernen hat nicht geklappt: {message}",open_source:"Zur Quelle",ingredients:"Zutaten",steps:"Zubereitung",servings:"{n} Portionen",servings_one:"1 Portion",prep_time:"Vorbereitung",cook_time:"Kochen",total_time:"Gesamt",to_shopping_list:"Auf die Einkaufsliste",shopping_hint:"Merke das Rezept mit dem Herz, dann kannst du es auf die Einkaufsliste setzen.",added_items:"{n} Zutaten stehen jetzt auf der Einkaufsliste.",added_items_one:"1 Zutat steht jetzt auf der Einkaufsliste.",added_none:"Es gab nichts Neues für die Einkaufsliste.",shopping_failed:"Einkaufsliste hat nicht geklappt: {message}",shopping_partial:"{done} von {total} Rezepten sind schon auf der Einkaufsliste. Bei den übrigen hat es nicht geklappt: {message} Sie bleiben ausgewählt, du kannst es noch einmal versuchen.",recipe_failed:"Das Rezept ließ sich nicht laden.",recipe_missing:"Auf dieser Seite steht kein Rezept, das EatFresh lesen kann.",collection_intro:"Deine Rezepte aus KitchenOwl. Tippe Rezepte an, um sie auszuwählen.",collection_empty:"Noch keine Rezepte in KitchenOwl. Merke dir Rezepte in der Suche mit dem Herz.",collection_failed:"Die Sammlung ließ sich nicht laden.",selected:"{n} ausgewählt",clear_selection:"Auswahl aufheben",open_recipe:"Rezept öffnen",select_recipe:"Auswählen",minutes:"{n} Min.",hours:"{h} Std.",hours_minutes:"{h} Std. {m} Min.",no_photo:"Kein Foto",close:"Schließen",err_source_error:"Die Rezeptseite hat einen Fehler gemeldet.",err_source_blocked:"Die Rezeptseite blockt gerade Abrufe. Bitte später noch mal versuchen.",err_not_found:"Dazu wurde kein Rezept gefunden.",err_kitchenowl_error:"KitchenOwl hat einen Fehler gemeldet.",err_kitchenowl_auth:"KitchenOwl hat den Zugang abgelehnt. Bitte den Zugang in den Einstellungen der Integration prüfen.",err_unknown:"Unbekannter Fehler."},ke={title:"EatFresh",menu:"Menu",nav_search:"Search",nav_collection:"Collection",nav_label:"Views",search_label:"Search recipes",search_placeholder:"What would you like to cook?",search_button:"Search",sources_label:"Sources",link_title:"Paste a recipe link",link_placeholder:"https://…",link_button:"Open",link_hint:"Link to a recipe on any website.",link_invalid:"That is not a valid link. It has to start with “https://”.",search_start:"Type what you feel like eating above, e.g. “pumpkin soup”.",search_empty:"No recipes found. Try another word.",search_no_sources:"Select at least one source.",source_failed:"“{source}” did not answer: {message}",loading:"Loading …",retry:"Try again",back:"Back",favorite_add:"Save",favorite_remove:"Remove from saved",favorite_failed:"Saving failed: {message}",unfavorite_failed:"Removing failed: {message}",open_source:"Open source",ingredients:"Ingredients",steps:"Instructions",servings:"{n} servings",servings_one:"1 serving",prep_time:"Prep",cook_time:"Cook",total_time:"Total",to_shopping_list:"Add to shopping list",shopping_hint:"Save the recipe with the heart, then you can add it to the shopping list.",added_items:"{n} ingredients are now on the shopping list.",added_items_one:"1 ingredient is now on the shopping list.",added_none:"There was nothing new for the shopping list.",shopping_failed:"Shopping list failed: {message}",shopping_partial:"{done} of {total} recipes are already on the shopping list. The others failed: {message} They stay selected, so you can try again.",recipe_failed:"The recipe could not be loaded.",recipe_missing:"This page has no recipe that EatFresh can read.",collection_intro:"Your recipes from KitchenOwl. Tap recipes to select them.",collection_empty:"No recipes in KitchenOwl yet. Save recipes in the search with the heart.",collection_failed:"The collection could not be loaded.",selected:"{n} selected",clear_selection:"Clear selection",open_recipe:"Open recipe",select_recipe:"Select",minutes:"{n} min",hours:"{h} h",hours_minutes:"{h} h {m} min",no_photo:"No photo",close:"Close",err_source_error:"The recipe website reported an error.",err_source_blocked:"The recipe website is blocking requests right now. Please try again later.",err_not_found:"No recipe was found.",err_kitchenowl_error:"KitchenOwl reported an error.",err_kitchenowl_auth:"KitchenOwl rejected the access. Please check the access in the integration settings.",err_unknown:"Unknown error."};function Se(e,t,i={}){return("de"===e?we:ke)[t].replace(/\{(\w+)\}/g,(e,t)=>t in i?String(i[t]):`{${t}}`)}const Ae=((e,...t)=>{const i=1===e.length?e[0]:t.reduce((t,i,s)=>t+(e=>{if(!0===e._$cssResult$)return e.cssText;if("number"==typeof e)return e;throw Error("Value passed to 'css' function must be a 'css' function result: "+e+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+e[s+1],e[0]);return new _(i,e,d)})`
  :host {
    --ef-primary: var(--primary-color, #03a9f4);
    --ef-on-primary: var(--text-primary-color, #fff);
    --ef-bg: var(--primary-background-color, #fafafa);
    --ef-card: var(--card-background-color, #fff);
    --ef-text: var(--primary-text-color, #212121);
    --ef-text2: var(--secondary-text-color, #727272);
    --ef-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --ef-error: var(--error-color, #db4437);
    --ef-success: var(--success-color, #43a047);
    --ef-radius: var(--ha-card-border-radius, 12px);
    --ef-header-bg: var(--app-header-background-color, var(--ef-bg));
    --ef-header-text: var(--app-header-text-color, var(--ef-text));
    --ef-tint: color-mix(in srgb, var(--ef-primary) 14%, transparent);
    --ef-tint-strong: color-mix(in srgb, var(--ef-primary) 24%, transparent);
    --ef-hover: color-mix(in srgb, var(--ef-text) 7%, transparent);
    display: block;
    height: 100dvh;
    max-width: 100%;
    overflow: hidden;
    background: var(--ef-bg);
    color: var(--ef-text);
    font-family: var(--ha-font-family-body, var(--mdc-typography-font-family, Roboto, system-ui, -apple-system, "Segoe UI", sans-serif));
    font-size: clamp(14px, calc(13px + 0.25vw), 16px);
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
    -webkit-tap-highlight-color: transparent;
  }
  *, *::before, *::after { box-sizing: border-box; }
  [hidden] { display: none !important; }

  .shell { display: flex; flex-direction: column; height: 100%; min-width: 0; }

  /* Header */
  .top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 4px;
    min-height: 56px;
    padding: 0 8px 0 4px;
    background: var(--ef-header-bg);
    color: var(--ef-header-text);
    border-bottom: 1px solid var(--ef-divider);
  }
  .top h1 {
    flex: 1;
    min-width: 0;
    margin: 0 0 0 12px;
    font-size: 1.25em;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .top .icon-btn + h1 { margin-left: 4px; }
  .top-nav { display: flex; gap: 4px; }

  /* Body with scrolling main area and toast layer */
  .body { position: relative; flex: 1; min-height: 0; display: flex; }
  main {
    flex: 1;
    min-width: 0;
    overflow-x: hidden;
    overflow-y: auto;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  }
  .content { width: 100%; max-width: 1120px; margin: 0 auto; padding: 16px; }
  /* Collection: the selection bar always sits at the bottom of the window,
     also when the list is short, so a hint above it never covers it. */
  .content.fill { min-height: 100%; display: flex; flex-direction: column; }
  .content.fill > .action-bar { margin-top: auto; }
  .content.fill > .grid { margin-bottom: 16px; }

  /* Bottom navigation (narrow layouts) */
  .bottom-nav {
    flex: none;
    display: flex;
    background: var(--ef-card);
    border-top: 1px solid var(--ef-divider);
  }
  .bottom-nav .nav-btn {
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-height: 56px;
    border-radius: 0;
    font-size: 0.8em;
  }

  /* Buttons */
  button, a.btn { font: inherit; color: inherit; }
  button { cursor: pointer; }
  button:disabled { cursor: default; opacity: 0.5; }
  .icon-btn {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
  }
  .icon-btn:hover { background: var(--ef-hover); }
  .nav-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 44px;
    min-width: 44px;
    padding: 0 14px;
    border: 0;
    border-radius: 22px;
    background: transparent;
    color: var(--ef-text2);
    font-weight: 500;
  }
  .nav-btn[aria-current="page"] { color: var(--ef-primary); }
  .top-nav .nav-btn[aria-current="page"] { background: var(--ef-tint); }
  .nav-btn:hover { background: var(--ef-hover); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 18px;
    border: 1px solid var(--ef-divider);
    border-radius: 22px;
    background: var(--ef-card);
    color: var(--ef-text);
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
  }
  .btn:hover { background: color-mix(in srgb, var(--ef-card) 90%, var(--ef-text)); }
  .btn.primary { background: var(--ef-primary); border-color: var(--ef-primary); color: var(--ef-on-primary); }
  .btn.primary:hover { background: color-mix(in srgb, var(--ef-primary) 88%, #000); }
  .btn.small { min-height: 44px; padding: 0 14px; }
  :focus-visible { outline: 2px solid var(--ef-primary); outline-offset: 2px; }
  svg.i { width: 24px; height: 24px; fill: currentColor; flex: none; }
  svg.i.s { width: 18px; height: 18px; }

  /* Search form */
  .search-form { display: flex; gap: 8px; }
  .field {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 48px;
    padding: 0 6px 0 12px;
    border: 1px solid var(--ef-divider);
    border-radius: 24px;
    background: var(--ef-card);
    color: var(--ef-text2);
  }
  .field:focus-within { border-color: var(--ef-primary); box-shadow: 0 0 0 1px var(--ef-primary); }
  .field input {
    flex: 1;
    min-width: 0;
    height: 46px;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--ef-text);
    font: inherit;
    font-size: max(16px, 1em); /* 16px stops iOS from zooming */
  }
  .field input::placeholder { color: var(--ef-text2); opacity: 0.8; }
  .search-form .btn { min-height: 48px; }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; padding: 0; border: 0; }
  .chips legend { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--ef-divider);
    border-radius: 22px;
    background: transparent;
    color: var(--ef-text);
    font-size: 0.93em;
  }
  .chip[aria-pressed="true"] { background: var(--ef-tint); border-color: transparent; color: var(--ef-text); }
  .chip svg.i { width: 18px; height: 18px; }

  .link-box { margin-top: 20px; padding: 14px 16px 16px; border-radius: var(--ef-radius); background: var(--ef-card); border: 1px solid var(--ef-divider); }
  .link-box h2 { margin: 0 0 2px; font-size: 1em; font-weight: 500; display: flex; gap: 8px; align-items: center; }
  .link-box p { margin: 0 0 10px; color: var(--ef-text2); font-size: 0.93em; }
  .link-box .field { min-height: 44px; }
  .link-box .field input { height: 42px; }

  /* Status messages */
  .note { margin: 28px auto; max-width: 34em; text-align: center; color: var(--ef-text2); }
  .note > svg.i { display: block; margin: 0 auto 8px; width: 40px; height: 40px; opacity: 0.6; }
  .note .btn { margin-top: 12px; }
  .banner {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin: 12px 0 0;
    padding: 10px 12px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--ef-error) 12%, transparent);
    color: var(--ef-text);
    font-size: 0.93em;
  }
  .banner svg.i { color: var(--ef-error); width: 20px; height: 20px; margin-top: 1px; }
  .banner.info { background: var(--ef-tint); }
  .banner.info svg.i { color: var(--ef-primary); }
  .error-text { color: var(--ef-error); }

  /* Recipe cards */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .wide .grid { grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 16px; }
  .card {
    position: relative;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-radius: var(--ef-radius);
    background: var(--ef-card);
    border: 1px solid var(--ef-divider);
    box-shadow: var(--ha-card-box-shadow, none);
  }
  .card-link {
    display: flex;
    flex-direction: column;
    flex: 1;
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    text-align: left;
    text-decoration: none;
  }
  .card-link:hover .card-title { color: var(--ef-primary); }
  .photo {
    position: relative;
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 4 / 3;
    overflow: hidden;
    background: color-mix(in srgb, var(--ef-primary) 10%, var(--ef-card));
    color: color-mix(in srgb, var(--ef-primary) 55%, var(--ef-card));
  }
  .photo svg.i { width: 36px; height: 36px; }
  .photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .card-body { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px 12px; min-width: 0; }
  .card-title {
    margin: 0;
    font-size: 1em;
    font-weight: 500;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: anywhere;
  }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; color: var(--ef-text2); font-size: 0.86em; min-width: 0; }
  .meta span { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
  .meta .src { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta svg.i { width: 16px; height: 16px; }
  .heart {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: #fff;
  }
  .heart::before {
    content: "";
    position: absolute;
    inset: 4px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.38);
  }
  .heart svg.i { position: relative; width: 22px; height: 22px; transition: transform 0.15s ease; }
  .heart[aria-pressed="true"] svg.i { color: #ff5a70; }
  .heart:active svg.i { transform: scale(0.85); }
  .heart.busy svg.i { opacity: 0.75; }

  /* Collection selection */
  .card.selectable .card-link { cursor: pointer; }
  .card.selected { border-color: var(--ef-primary); box-shadow: 0 0 0 2px var(--ef-primary); }
  .check {
    position: absolute;
    top: 10px;
    left: 10px;
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    border: 2px solid #fff;
    background: rgba(0, 0, 0, 0.3);
    color: #fff;
  }
  .card.selected .check { background: var(--ef-primary); border-color: var(--ef-primary); color: var(--ef-on-primary); }
  .check svg.i { width: 18px; height: 18px; }
  .open-btn {
    position: absolute;
    top: 4px;
    right: 4px;
    color: #fff;
  }
  .open-btn::before { content: ""; position: absolute; inset: 4px; border-radius: 50%; background: rgba(0, 0, 0, 0.38); }
  .open-btn svg.i { position: relative; width: 20px; height: 20px; }
  .intro { margin: 0; color: var(--ef-text2); }

  .action-bar {
    position: sticky;
    bottom: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 16px -16px -16px;
    padding: 10px 16px;
    background: color-mix(in srgb, var(--ef-card) 94%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-top: 1px solid var(--ef-divider);
  }
  .action-bar .count { flex: 1; min-width: 0; font-weight: 500; }
  .action-bar .btn.primary { flex: none; }

  /* Recipe view */
  .recipe-head { display: grid; gap: 16px; }
  .wide .recipe-head { grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); align-items: start; gap: 24px; }
  .hero { border-radius: var(--ef-radius); aspect-ratio: 16 / 10; }
  .hero svg.i { width: 48px; height: 48px; }
  .recipe-title { margin: 0; font-size: 1.5em; font-weight: 500; line-height: 1.25; overflow-wrap: anywhere; }
  .recipe-desc { margin: 8px 0 0; color: var(--ef-text2); }
  .facts { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
  .facts li {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 16px;
    background: var(--ef-tint);
    font-size: 0.9em;
  }
  .facts svg.i { width: 16px; height: 16px; color: var(--ef-primary); }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .btn.fav[aria-pressed="true"] svg.i { color: #e2405a; }
  .hint { margin: 10px 0 0; color: var(--ef-text2); font-size: 0.9em; }
  .recipe-body { display: grid; gap: 16px; margin-top: 20px; }
  .wide .recipe-body { grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 24px; align-items: start; }
  .panel-box { padding: 16px; border-radius: var(--ef-radius); background: var(--ef-card); border: 1px solid var(--ef-divider); min-width: 0; }
  .panel-box h2 { margin: 0 0 8px; font-size: 1.1em; font-weight: 500; }
  .ingredients { margin: 0; padding: 0; list-style: none; }
  .ingredients li { display: flex; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--ef-divider); overflow-wrap: anywhere; }
  .ingredients li:last-child { border-bottom: 0; }
  .ingredients .qty { flex: none; width: 6.5em; color: var(--ef-text2); font-variant-numeric: tabular-nums; }
  .ingredients .note { margin: 0; text-align: left; color: var(--ef-text2); }
  .steps { margin: 0; padding: 0; list-style: none; counter-reset: step; }
  .steps li { position: relative; padding: 4px 0 14px 44px; counter-increment: step; overflow-wrap: anywhere; }
  .steps li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 0;
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--ef-tint);
    color: var(--ef-primary);
    font-weight: 500;
    font-size: 0.9em;
  }
  .back-row { margin: -4px 0 12px -8px; }
  .back-row .nav-btn { color: var(--ef-text); padding-left: 8px; }

  /* Skeletons */
  .skel { background: var(--ef-hover); border-radius: 6px; animation: pulse 1.4s ease-in-out infinite; }
  .skel.line { height: 0.9em; margin: 6px 0; }
  .skel.line.short { width: 55%; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) {
    .skel { animation: none; }
    .heart svg.i { transition: none; }
  }

  /* Toast */
  .toast {
    position: absolute;
    left: 50%;
    bottom: 16px;
    z-index: 5;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 8px;
    width: max-content;
    max-width: calc(100% - 32px);
    padding: 4px 4px 4px 16px;
    border-radius: 12px;
    background: color-mix(in srgb, var(--ef-text) 90%, var(--ef-bg));
    color: var(--ef-bg);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  }
  .toast.raised { bottom: 84px; }
  .toast .msg { flex: 1; min-width: 0; padding: 8px 0; overflow-wrap: anywhere; }
  .toast .icon-btn:hover { background: rgba(127, 127, 127, 0.25); }
  .toast.error .lead { color: color-mix(in srgb, var(--ef-error) 70%, var(--ef-bg)); }
  .toast.ok .lead { color: color-mix(in srgb, var(--ef-success) 70%, var(--ef-bg)); }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
`;function Ce(e,t){if(null==t||!Number.isFinite(t)||t<=0)return"";const i=Math.round(t),s=Math.floor(i/60),r=i%60;return 0===s?Se(e,"minutes",{n:r}):0===r?Se(e,"hours",{h:s}):Se(e,"hours_minutes",{h:s,m:r})}function Ee(e,t){if(null==t)return"";const i={.25:"¼",.5:"½",.75:"¾"},s=Math.floor(t),r=+(t-s).toFixed(2);return i[String(r)]?`${s>0?s:""}${i[String(r)]}`:t.toLocaleString("de"===e?"de-DE":"en-US",{maximumFractionDigits:2})}function Le(e){if(!e)return"";try{return new URL(e).hostname.replace(/^www\./,"")}catch{return e}}function Me(e){try{const t=new URL(e.trim());return"https:"===t.protocol||"http:"===t.protocol}catch{return!1}}function He(e,t){const i=t??{};switch(i.code){case"source_error":return Se(e,"err_source_error");case"source_blocked":return Se(e,"err_source_blocked");case"not_found":return Se(e,"err_not_found");case"kitchenowl_error":return Se(e,"err_kitchenowl_error");case"kitchenowl_auth":return Se(e,"err_kitchenowl_auth");default:return i.message||Se(e,"err_unknown")}}function Te(e){const t=e.replace(/^\/+/,"").split("/"),i=e=>{try{return decodeURIComponent(e??"")}catch{return""}};switch(t[0]){case"collection":return{name:"collection"};case"recipe":{const e=i(t.slice(1).join("/"));return e?{name:"recipe",key:e}:{name:"search"}}case"link":{const e=i(t.slice(1).join("/"));return e?{name:"recipe",url:e}:{name:"search"}}default:return{name:"search"}}}function Re(e){if("collection"===e.name)return"/collection";if("recipe"===e.name){if(e.key)return`/recipe/${encodeURIComponent(e.key)}`;if(e.url)return`/link/${encodeURIComponent(e.url)}`}return"/search"}const ze=(e,t="i")=>X`<svg class=${t} viewBox="0 0 24 24" aria-hidden="true">${Y`<path d=${e}></path>`}</svg>`;class Pe extends ve{constructor(){super(...arguments),this.narrow=!1,this._lang="en",this._wide=!1,this._view={name:"search"},this._sources=[],this._sourcesState="idle",this._sourcesError="",this._selectedSources=new Set,this._query="",this._hits=[],this._searchErrors=[],this._searchState="idle",this._searchError="",this._linkInvalid=!1,this._recipeFor="",this._recipeState="idle",this._recipeError="",this._recipeMissing=!1,this._collection=[],this._collectionState="idle",this._collectionError="",this._selected=new Set,this._favs=new Map,this._favBusy=new Set,this._shoppingBusy=!1,this._searchSeq=0,this._recipeSeq=0,this._navigatedInside=!1,this._collectionStale=!0,this._onPopState=()=>{const{pathname:e}=window.location;e.startsWith(this._prefix)&&this._applyView(Te(e.slice(this._prefix.length)))}}static{this.styles=Ae}get hass(){return this._hass}set hass(e){const t=!this._hass&&!!e;this._hass=e;const i=(e?.language??e?.locale?.language??"").toLowerCase().startsWith("de")?"de":"en";i!==this._lang&&(this._lang=i),t&&this._loadSources()}connectedCallback(){super.connectedCallback(),window.addEventListener("popstate",this._onPopState),this._resize=new ResizeObserver(e=>{const t=(e[0]?.contentRect.width??0)>=600;t!==this._wide&&(this._wide=t)}),this._resize.observe(this)}disconnectedCallback(){super.disconnectedCallback(),window.removeEventListener("popstate",this._onPopState),this._resize?.disconnect(),window.clearTimeout(this._toastTimer)}willUpdate(e){e.has("route")&&this.route&&this._applyView(Te(this.route.path??""))}_t(e,t){return Se(this._lang,e,t)}get _prefix(){return this.route?.prefix??"/eatfresh"}_navigate(e,t=!1){const i=this._prefix+Re(e);i!==window.location.pathname&&(t?window.history.replaceState(window.history.state,"",i):window.history.pushState(null,"",i),t||(this._navigatedInside=!0),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:t}}))),this._applyView(e)}_applyView(e){const t=this._view;t.name===e.name&&("recipe"!==e.name||"recipe"===t.name&&t.key===e.key&&t.url===e.url)||(this._view=e,window.clearTimeout(this._toastTimer),this._toast=void 0,this.renderRoot.querySelector("main")?.scrollTo({top:0})),"recipe"===e.name&&this._loadRecipe(e),"collection"!==e.name||!this._collectionStale&&"error"!==this._collectionState||this._loadCollection()}_back(){this._navigatedInside&&window.history.length>1?window.history.back():this._navigate({name:"search"},!0)}_toggleMenu(){this.dispatchEvent(new CustomEvent("hass-toggle-menu",{bubbles:!0,composed:!0}))}async _ws(e){if(!this._hass)throw{code:"not_ready",message:""};return this._hass.callWS(e)}async _loadSources(){this._sourcesState="loading";try{const e=await this._ws({type:"eatfresh/sources"});this._sources=e.sources,this._selectedSources=new Set(e.sources.filter(e=>e.enabled&&e.searchable).map(e=>e.id)),this._sourcesState="done"}catch(e){this._sourcesError=He(this._lang,e),this._sourcesState="error"}}_sourceName(e){return this._sources.find(t=>t.id===e)?.name??e}get _searchable(){return this._sources.filter(e=>e.enabled&&e.searchable)}async _search(){const e=this._query.trim();if(!e)return;if(Me(e))return void this._openLink(e);if(this._searchable.length&&!this._selectedSources.size)return;const t=++this._searchSeq;this._searchState="loading",this._searchError="",this._searchErrors=[];try{const i={type:"eatfresh/search",query:e};this._searchable.length&&(i.sources=[...this._selectedSources]);const s=await this._ws(i);if(t!==this._searchSeq)return;this._hits=s.hits??[],this._searchErrors=s.errors??[];for(const e of this._hits)this._favs.delete(e.key);this._searchState="done"}catch(e){if(t!==this._searchSeq)return;this._hits=[],this._searchError=He(this._lang,e),this._searchState="error"}}_openLink(e){const t=e.trim();Me(t)?(this._linkInvalid=!1,this._navigate({name:"recipe",url:t})):this._linkInvalid=!0}async _loadRecipe(e,t=!1){const i=e.key?`k:${e.key}`:`u:${e.url}`;if(!t&&i===this._recipeFor&&"error"!==this._recipeState)return;this._recipeFor=i;const s=++this._recipeSeq;this._recipe=void 0,this._recipeState="loading";try{const t=e.key?{type:"eatfresh/recipe",key:e.key}:{type:"eatfresh/recipe",url:e.url},i=await this._ws(t);if(s!==this._recipeSeq)return;this._recipe=i,this._favs.delete(i.recipe.key),this._recipeState="done"}catch(e){if(s!==this._recipeSeq)return;this._recipeError=He(this._lang,e),this._recipeMissing="not_found"===e?.code,this._recipeState="error"}}async _loadCollection(){this._collectionState="loading",this._collectionStale=!1;try{const e=await this._ws({type:"eatfresh/collection"});this._collection=e.recipes??[];const t=new Set(this._collection.map(e=>e.kitchenowl_id));this._selected=new Set([...this._selected].filter(e=>t.has(e))),this._collectionState="done"}catch(e){this._collectionError=He(this._lang,e),this._collectionState="error",this._collectionStale=!0}}_isFav(e,t){return this._favs.get(e)??t}async _toggleFav(e,t){if(this._favBusy.has(e))return;const i=!t;this._favs=new Map(this._favs).set(e,i),this._favBusy=new Set(this._favBusy).add(e);try{if(i){const t=await this._ws({type:"eatfresh/favorite",key:e});this._recipe?.recipe.key===e&&(this._recipe={...this._recipe,favorite:!0,kitchenowl_id:t.kitchenowl_id})}else await this._ws({type:"eatfresh/unfavorite",key:e}),this._recipe?.recipe.key===e&&(this._recipe={...this._recipe,favorite:!1});this._collectionStale=!0}catch(s){this._favs=new Map(this._favs).set(e,t),this._showToast(this._t(i?"favorite_failed":"unfavorite_failed",{message:He(this._lang,s)}),"error")}finally{const t=new Set(this._favBusy);t.delete(e),this._favBusy=t}}async _addToShopping(e){if(e.length&&!this._shoppingBusy){this._shoppingBusy=!0;try{const t=(await this._ws({type:"eatfresh/shopping_list/add",kitchenowl_ids:e})).added??0;this._showToast(0===t?this._t("added_none"):1===t?this._t("added_items_one"):this._t("added_items",{n:t}),"ok"),"collection"===this._view.name&&(this._selected=new Set)}catch(t){const i=t??{},s=Number(i.translation_placeholders?.added_recipes??0);if("shopping_list_partial"===i.translation_key&&s>0){if("collection"===this._view.name){const t=new Set(e.slice(0,s));this._selected=new Set([...this._selected].filter(e=>!t.has(e)))}this._showToast(this._t("shopping_partial",{done:s,total:e.length,message:He(this._lang,t)}),"error")}else this._showToast(this._t("shopping_failed",{message:He(this._lang,t)}),"error")}finally{this._shoppingBusy=!1}}}_showToast(e,t){window.clearTimeout(this._toastTimer),this._toast={text:e,kind:t,id:Date.now()},this._toastTimer=window.setTimeout(()=>this._toast=void 0,4500)}render(){const e=this._view.name,t="collection"===e?"collection":"search",i=X`
      <button
        class="nav-btn"
        aria-current=${"search"===t?"page":"false"}
        @click=${()=>this._navigate({name:"search"})}
      >
        ${ze(a)}<span>${this._t("nav_search")}</span>
      </button>
      <button
        class="nav-btn"
        aria-current=${"collection"===t?"page":"false"}
        @click=${()=>this._navigate({name:"collection"})}
      >
        ${ze("M19 1L14 6V17L19 12.5V1M21 5V18.5C19.9 18.15 18.7 18 17.5 18C15.8 18 13.35 18.65 12 19.5V6C10.55 4.9 8.45 4.5 6.5 4.5C4.55 4.5 2.45 4.9 1 6V20.65C1 20.9 1.25 21.15 1.5 21.15C1.6 21.15 1.65 21.1 1.75 21.1C3.1 20.45 5.05 20 6.5 20C8.45 20 10.55 20.4 12 21.5C13.35 20.65 15.8 20 17.5 20C19.15 20 20.85 20.3 22.25 21.05C22.35 21.1 22.4 21.1 22.5 21.1C22.75 21.1 23 20.85 23 20.6V6C22.4 5.55 21.75 5.25 21 5M10 18.41C8.75 18.09 7.5 18 6.5 18C5.44 18 4.18 18.19 3 18.5V7.13C3.91 6.73 5.14 6.5 6.5 6.5C7.86 6.5 9.09 6.73 10 7.13V18.41Z")}<span>${this._t("nav_collection")}</span>
      </button>
    `;return X`
      <div class="shell ${this._wide?"wide":"narrow"}">
        <header class="top">
          ${this.narrow?X`<button class="icon-btn" aria-label=${this._t("menu")} @click=${this._toggleMenu}>
                ${ze("M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z")}
              </button>`:te}
          <h1>${this._t("title")}</h1>
          ${this._wide?X`<nav class="top-nav" aria-label=${this._t("nav_label")}>${i}</nav>`:te}
        </header>
        <div class="body">
          <main>
            <div class="content ${"collection"===e?"fill":""}">
              ${"search"===e?this._renderSearch():"recipe"===e?this._renderRecipe():this._renderCollection()}
            </div>
          </main>
          ${this._renderToast()}
        </div>
        ${this._wide?te:X`<nav class="bottom-nav" aria-label=${this._t("nav_label")}>${i}</nav>`}
      </div>
    `}_renderToast(){const e=this._toast,i="collection"===this._view.name&&this._selected.size>0;return X`<div class="sr" role="status" aria-live="polite">${e?.text??""}</div>
      ${e?X`<div class="toast ${e.kind} ${i?"raised":""}">
            <span class="lead">${ze("ok"===e.kind?"M12 2C6.5 2 2 6.5 2 12S6.5 22 12 22 22 17.5 22 12 17.5 2 12 2M12 20C7.59 20 4 16.41 4 12S7.59 4 12 4 20 7.59 20 12 16.41 20 12 20M16.59 7.58L10 14.17L7.41 11.59L6 13L10 17L18 9L16.59 7.58Z":t)}</span>
            <span class="msg">${e.text}</span>
            <button class="icon-btn" aria-label=${this._t("close")} @click=${()=>this._toast=void 0}>
              ${ze(n)}
            </button>
          </div>`:te}`}_photo(e,t=""){return X`<div class="photo ${t}">
      ${ze(c)}
      ${e?X`<img
            src=${e}
            alt=""
            loading="lazy"
            decoding="async"
            @error=${e=>e.target.hidden=!0}
          />`:te}
    </div>`}_heart(e,t,i="heart"){const s=this._favBusy.has(e);return X`<button
      class="${i} ${s?"busy":""}"
      aria-pressed=${t?"true":"false"}
      aria-label=${this._t(t?"favorite_remove":"favorite_add")}
      title=${this._t(t?"favorite_remove":"favorite_add")}
      @click=${i=>{i.preventDefault(),i.stopPropagation(),this._toggleFav(e,t)}}
    >
      ${ze(t?"M12,21.35L10.55,20.03C5.4,15.36 2,12.27 2,8.5C2,5.41 4.42,3 7.5,3C9.24,3 10.91,3.81 12,5.08C13.09,3.81 14.76,3 16.5,3C19.58,3 22,5.41 22,8.5C22,12.27 18.6,15.36 13.45,20.03L12,21.35Z":o)}${i.includes("btn")?X`<span>${this._t(t?"favorite_remove":"favorite_add")}</span>`:te}
    </button>`}_skeletonCards(e=6){return X`<div class="grid" aria-busy="true" aria-label=${this._t("loading")}>
      ${Array.from({length:e},()=>X`<div class="card">
          <div class="photo skel" style="border-radius:0"></div>
          <div class="card-body"><div class="skel line"></div><div class="skel line short"></div></div>
        </div>`)}
    </div>`}_note(e,t=c,i){return X`<div class="note">
      ${ze(t)}
      <div>${e}</div>
      ${i?X`<button class="btn" @click=${i}>${this._t("retry")}</button>`:te}
    </div>`}_renderSearch(){const e=this._searchable;return X`
      <form
        class="search-form"
        role="search"
        @submit=${e=>{e.preventDefault(),this._search()}}
      >
        <label class="field">
          ${ze(a)}
          <span class="sr">${this._t("search_label")}</span>
          <input
            type="search"
            enterkeyhint="search"
            autocomplete="off"
            .value=${this._query}
            placeholder=${this._t("search_placeholder")}
            @input=${e=>this._query=e.target.value}
          />
        </label>
        <button class="btn primary" type="submit" aria-label=${this._t("search_button")}>
          ${this._wide?this._t("search_button"):ze(a)}
        </button>
      </form>
      ${"error"===this._sourcesState?X`<div class="banner">
            ${ze(t)}<span>${this._sourcesError}</span>
          </div>`:te}
      ${e.length>1?X`<fieldset class="chips">
            <legend>${this._t("sources_label")}</legend>
            ${e.map(e=>{const t=this._selectedSources.has(e.id);return X`<button
                type="button"
                class="chip"
                aria-pressed=${t?"true":"false"}
                @click=${()=>{const i=new Set(this._selectedSources);t?i.delete(e.id):i.add(e.id),this._selectedSources=i}}
              >
                ${t?ze(s):te}${e.name}
              </button>`})}
          </fieldset>`:te}
      ${this._renderResults()}
      <section class="link-box">
        <h2>${ze("M10.59,13.41C11,13.8 11,14.44 10.59,14.83C10.2,15.22 9.56,15.22 9.17,14.83C7.22,12.88 7.22,9.71 9.17,7.76V7.76L12.71,4.22C14.66,2.27 17.83,2.27 19.78,4.22C21.73,6.17 21.73,9.34 19.78,11.29L18.29,12.78C18.3,11.96 18.17,11.14 17.89,10.36L18.36,9.88C19.54,8.71 19.54,6.81 18.36,5.64C17.19,4.46 15.29,4.46 14.12,5.64L10.59,9.17C9.41,10.34 9.41,12.24 10.59,13.41M13.41,9.17C13.8,8.78 14.44,8.78 14.83,9.17C16.78,11.12 16.78,14.29 14.83,16.24V16.24L11.29,19.78C9.34,21.73 6.17,21.73 4.22,19.78C2.27,17.83 2.27,14.66 4.22,12.71L5.71,11.22C5.7,12.04 5.83,12.86 6.11,13.65L5.64,14.12C4.46,15.29 4.46,17.19 5.64,18.36C6.81,19.54 8.71,19.54 9.88,18.36L13.41,14.83C14.59,13.66 14.59,11.76 13.41,10.59C13,10.2 13,9.56 13.41,9.17Z","i s")}${this._t("link_title")}</h2>
        <p>${this._t("link_hint")}</p>
        <form
          class="search-form"
          novalidate
          @submit=${e=>{e.preventDefault();const t=e.target.querySelector("input");this._openLink(t?.value??"")}}
        >
          <label class="field">
            <span class="sr">${this._t("link_title")}</span>
            <input
              type="url"
              inputmode="url"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              placeholder=${this._t("link_placeholder")}
              aria-invalid=${this._linkInvalid?"true":"false"}
              @input=${()=>this._linkInvalid=!1}
            />
          </label>
          <button class="btn" type="submit">${this._t("link_button")}</button>
        </form>
        ${this._linkInvalid?X`<p class="error-text" role="alert">${this._t("link_invalid")}</p>`:te}
      </section>
    `}_renderResults(){const e=this._searchErrors.map(e=>X`<div class="banner">
        ${ze(t)}
        <span>${this._t("source_failed",{source:this._sourceName(e.source),message:e.message})}</span>
      </div>`);if(this._searchable.length>1&&!this._selectedSources.size)return X`<div class="banner info">${ze(t)}<span>${this._t("search_no_sources")}</span></div>`;switch(this._searchState){case"idle":return this._note(this._t("search_start"),a);case"loading":return this._skeletonCards();case"error":return this._note(this._searchError,t,()=>this._search());default:return X`${e}
          ${this._hits.length?X`<div class="grid">${this._hits.map(e=>this._renderHit(e))}</div>`:this._note(this._t("search_empty"))}`}}_renderHit(e){const t=this._isFav(e.key,e.favorite),i=Ce(this._lang,e.total_time),s={name:"recipe",key:e.key};return X`<article class="card">
      <a
        class="card-link"
        href=${this._prefix+Re(s)}
        @click=${e=>{e.metaKey||e.ctrlKey||e.shiftKey||0!==e.button||(e.preventDefault(),this._navigate(s))}}
      >
        ${this._photo(e.image)}
        <div class="card-body">
          <h3 class="card-title">${e.title}</h3>
          <div class="meta">
            ${i?X`<span>${ze(r)}${i}</span>`:te}
            <span class="src">${this._sourceName(e.source)}</span>
          </div>
        </div>
      </a>
      ${this._heart(e.key,t)}
    </article>`}_renderRecipe(){const e=X`<div class="back-row">
      <button class="nav-btn" @click=${this._back}>${ze("M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z")}<span>${this._t("back")}</span></button>
    </div>`;if("error"===this._recipeState){const i=this._view;if(this._recipeMissing){const t=i.url??this._hits.find(e=>e.key===i.key)?.url;return X`${e}<div class="note">
            ${ze(c)}
            <div>${this._t("recipe_missing")}</div>
            ${t&&Me(t)?X`<a class="btn" href=${t} target="_blank" rel="noopener noreferrer">
                  ${ze(l)}<span>${this._t("open_source")}</span>
                </a>`:te}
          </div>`}return X`${e}${this._note(`${this._t("recipe_failed")} ${this._recipeError}`,t,()=>this._loadRecipe(i,!0))}`}const s=this._recipe;if(!s||"loading"===this._recipeState)return X`${e}
        <div class="recipe-head" aria-busy="true" aria-label=${this._t("loading")}>
          <div class="photo hero skel"></div>
          <div>
            <div class="skel line" style="height:1.6em"></div>
            <div class="skel line short"></div>
            <div class="skel line"></div>
          </div>
        </div>`;const n=s.recipe,o=this._isFav(n.key,s.favorite),a=[],h=Ce(this._lang,n.total_time),p=Ce(this._lang,n.prep_time),d=Ce(this._lang,n.cook_time);h&&a.push([this._t("total_time"),h]),p&&a.push([this._t("prep_time"),p]),d&&a.push([this._t("cook_time"),d]);const u=null==n.servings?"":1===n.servings?this._t("servings_one"):this._t("servings",{n:n.servings}),_=s.kitchenowl_id;return X`${e}
      <div class="recipe-head">
        ${this._photo(n.image,"hero")}
        <div>
          <h2 class="recipe-title">${n.title}</h2>
          <div class="meta" style="margin-top:4px">
            <span class="src">${"jsonld"===n.source?Le(n.url):this._sourceName(n.source)}</span>
          </div>
          ${n.description?X`<p class="recipe-desc">${n.description}</p>`:te}
          ${a.length||u?X`<ul class="facts">
                ${a.map(([e,t])=>X`<li>${ze(r)}${e}: ${t}</li>`)}
                ${u?X`<li>${ze(c)}${u}</li>`:te}
              </ul>`:te}
          <div class="actions">
            ${this._heart(n.key,o,"btn fav")}
            ${Me(n.url)?X`<a class="btn" href=${n.url} target="_blank" rel="noopener noreferrer">
                  ${ze(l)}<span>${this._t("open_source")}</span>
                </a>`:te}
            ${null!=_?X`<button
                  class="btn primary"
                  ?disabled=${this._shoppingBusy}
                  @click=${()=>this._addToShopping([_])}
                >
                  ${ze(i)}<span>${this._t("to_shopping_list")}</span>
                </button>`:te}
          </div>
          ${null==_?X`<p class="hint">${this._t("shopping_hint")}</p>`:te}
        </div>
      </div>
      <div class="recipe-body">
        ${n.ingredients.length?X`<section class="panel-box">
              <h2>${this._t("ingredients")}</h2>
              <ul class="ingredients">
                ${n.ingredients.map(e=>{const t=function(e,t){return[Ee(e,t.amount),t.unit??""].filter(Boolean).join(" ")}(this._lang,e);return X`<li>
                    <span class="qty">${t}</span>
                    <span>${e.name||e.raw}${e.note?X` <span class="note">(${e.note})</span>`:te}</span>
                  </li>`})}
              </ul>
            </section>`:te}
        ${n.steps.length?X`<section class="panel-box">
              <h2>${this._t("steps")}</h2>
              <ol class="steps">
                ${n.steps.map(e=>X`<li>${e}</li>`)}
              </ol>
            </section>`:te}
      </div>`}_renderCollection(){if("loading"===this._collectionState||"idle"===this._collectionState)return X`<p class="intro">${this._t("collection_intro")}</p>${this._skeletonCards()}`;if("error"===this._collectionState)return this._note(`${this._t("collection_failed")} ${this._collectionError}`,t,()=>this._loadCollection());if(!this._collection.length)return this._note(this._t("collection_empty"),o);const e=this._selected.size;return X`<p class="intro">${this._t("collection_intro")}</p>
      <div class="grid">${this._collection.map(e=>this._renderCollectionCard(e))}</div>
      ${e?X`<div class="action-bar">
            <button class="icon-btn" aria-label=${this._t("clear_selection")} @click=${()=>this._selected=new Set}>
              ${ze(n)}
            </button>
            <span class="count">${this._t("selected",{n:e})}</span>
            <button
              class="btn primary"
              ?disabled=${this._shoppingBusy}
              @click=${()=>this._addToShopping([...this._selected])}
            >
              ${ze(i)}<span>${this._t("to_shopping_list")}</span>
            </button>
          </div>`:te}`}_renderCollectionCard(e){const t=this._selected.has(e.kitchenowl_id),i=Ce(this._lang,e.time),n=e.source&&Me(e.source)?e.source:null;return X`<article class="card selectable ${t?"selected":""}">
      <button class="card-link" role="checkbox" aria-checked=${t?"true":"false"} @click=${()=>{const i=new Set(this._selected);t?i.delete(e.kitchenowl_id):i.add(e.kitchenowl_id),this._selected=i}}>
        ${this._photo(e.image)}
        <div class="card-body">
          <h3 class="card-title">${e.name}</h3>
          <div class="meta">
            ${i?X`<span>${ze(r)}${i}</span>`:te}
            ${n?X`<span class="src">${Le(n)}</span>`:te}
          </div>
        </div>
        <span class="check" aria-hidden="true">${t?ze(s):te}</span>
      </button>
      ${n?X`<button
            class="icon-btn open-btn"
            aria-label=${`${this._t("open_recipe")}: ${e.name}`}
            title=${this._t("open_recipe")}
            @click=${()=>this._navigate({name:"recipe",url:n})}
          >
            ${ze(l)}
          </button>`:te}
    </article>`}}e([$e({type:Boolean,reflect:!0})],Pe.prototype,"narrow",void 0),e([$e({attribute:!1})],Pe.prototype,"route",void 0),e([$e({attribute:!1})],Pe.prototype,"panel",void 0),e([xe()],Pe.prototype,"_lang",void 0),e([xe()],Pe.prototype,"_wide",void 0),e([xe()],Pe.prototype,"_view",void 0),e([xe()],Pe.prototype,"_sources",void 0),e([xe()],Pe.prototype,"_sourcesState",void 0),e([xe()],Pe.prototype,"_sourcesError",void 0),e([xe()],Pe.prototype,"_selectedSources",void 0),e([xe()],Pe.prototype,"_query",void 0),e([xe()],Pe.prototype,"_hits",void 0),e([xe()],Pe.prototype,"_searchErrors",void 0),e([xe()],Pe.prototype,"_searchState",void 0),e([xe()],Pe.prototype,"_searchError",void 0),e([xe()],Pe.prototype,"_linkInvalid",void 0),e([xe()],Pe.prototype,"_recipe",void 0),e([xe()],Pe.prototype,"_recipeFor",void 0),e([xe()],Pe.prototype,"_recipeState",void 0),e([xe()],Pe.prototype,"_recipeError",void 0),e([xe()],Pe.prototype,"_recipeMissing",void 0),e([xe()],Pe.prototype,"_collection",void 0),e([xe()],Pe.prototype,"_collectionState",void 0),e([xe()],Pe.prototype,"_collectionError",void 0),e([xe()],Pe.prototype,"_selected",void 0),e([xe()],Pe.prototype,"_favs",void 0),e([xe()],Pe.prototype,"_favBusy",void 0),e([xe()],Pe.prototype,"_shoppingBusy",void 0),e([xe()],Pe.prototype,"_toast",void 0),customElements.get("eatfresh-panel")||customElements.define("eatfresh-panel",Pe);export{Pe as EatFreshPanel};
