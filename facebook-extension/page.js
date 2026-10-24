// All page operations are scoped to a dedicated Facebook tab created for one
// explicit export. No page-supplied script, selector, or executable code is run.
export function facebookPage(action, input = {}) {
  const text = element => (element?.getAttribute("aria-label") || element?.innerText || element?.textContent || "").replace(/\s+/g," ").trim();
  const visible = element => Boolean(element && element.getClientRects().length && getComputedStyle(element).visibility !== "hidden");
  const all = (root, selector) => [...root.querySelectorAll(selector)].filter(visible);
  const labels = {
    edit: /^(Edit profile|Modifier le profil|Editar perfil|עריכת פרופיל|تعديل الملف الشخصي)$/i,
    create: /^(What['’]s on your mind|Create (a )?post|Que voulez-vous|¿Qué estás pensando|על מה|بم تفكر)/i,
    photo: /^(Photo\/video|Photo\/vidéo|Foto\/video|תמונה\/סרטון|صورة\/فيديو)$/i,
    post: /^(Post|Publish|Share now|Publier|Publicar|פרסום|نشر)$/i,
    next: /^(Next|Suivant|Siguiente|הבא|التالي)$/i,
    done: /^(Done|Save|Terminé|Enregistrer|Listo|Guardar|סיום|שמירה|تم|حفظ)$/i,
    audience: {only_me:/^(Only me|Moi uniquement|Solo yo|רק אני|أنا فقط)$/i,
               friends:/^(Friends|Amis|Amigos|חברים|الأصدقاء)$/i,
               public:/^(Public|Público|ציבורי|العامة)$/i},
  };
  const buttons = root => all(root, "button,[role=button]");
  const findButton = (root, pattern) => buttons(root).find(element => pattern.test(text(element)) && element.getAttribute("aria-disabled") !== "true" && !element.disabled);
  const matches = (element, pattern) => pattern.test(text(element)) || pattern.test((element.innerText||element.textContent||"").replace(/\s+/g," ").trim());
  const accessibleLabel = element => (element.getAttribute("aria-labelledby")||"").split(/\s+/).map(id=>document.getElementById(id)?.textContent||"").join(" ");
  const normCaption = value => value.replace(/\r\n/g,"\n").replace(/\u00a0/g," ").trim();
  const stop = message => ({error:message});
  if (location.origin !== "https://www.facebook.com") return stop("Posting stopped because the browser left Facebook.");
  if (/\/(login|checkpoint|two_step_verification|recover)(\/|\.php|$)/i.test(location.pathname) || document.querySelector('input[type=password]'))
    return stop("Sign in or complete Facebook's security check yourself, then start the export again. ClipHarbor does not fill authentication dialogs.");

  const ownLink = all(document,'a[href],button,[role=button]').find(element=>labels.edit.test(text(element)));
  if(action === "profile") {
    if(!ownLink) return stop("Open your own profile and wait for Edit profile to appear, then connect again. Other people's profiles cannot be connected.");
    let name = "";
    for(let parent=ownLink.parentElement,depth=0;parent&&depth<7;parent=parent.parentElement,depth++) {
      const candidates = all(parent,"h1,h2,button,[role=button]").map(text).filter(value=>value.length>1&&value.length<=120&&!labels.edit.test(value)&&!/(Add to story|See Recommendations|Edit cover|Profile picture|Notifications)/i.test(value));
      if(candidates.length) { name=candidates[0]; break; }
    }
    return name ? {profileUrl:location.href,name} : stop("The profile name could not be verified. Refresh your own profile and try again.");
  }
  const dialogs = all(document,'[role=dialog]');
  const captionBox = root => all(root,'[contenteditable=true][role=textbox],textarea').find(element=>!/comment|search|commentaire|تعليق|תגובה/i.test(element.getAttribute("aria-label")||element.getAttribute("placeholder")||""));
  let composer = dialogs.find(element=>captionBox(element)||/Create (post|reel)|Créer|Crear|יצירת|إنشاء/i.test(text(element).slice(0,100)));
  if(!composer) {
    const main = all(document,'[role=main],main').find(element=>/Create (a )?reel|Describe your reel|Reel settings/i.test(text(element).slice(0,500)));
    if(main) composer=main;
  }
  if(action === "open") {
    if(!ownLink) return {waiting:"Waiting for your own profile to load"};
    if(composer) return {opened:true};
    const button = findButton(document,labels.create);
    if(!button) return stop("Facebook's post composer could not be recognized. If Facebook has an unfinished draft, finish or save it yourself first; ClipHarbor will not overwrite it.");
    button.click(); return {waiting:"Opening Facebook's post composer"};
  }
  if(action === "prepare") {
    if(!composer) return {waiting:"Waiting for the post composer"};
    const box=captionBox(composer);
    if(box && normCaption(box.innerText||box.value||""))
      return stop("Facebook already has a different draft. It was left untouched. Finish or save that draft yourself before exporting this video.");
    if(buttons(composer).some(element=>/Remove (Post )?Attachment|Edit photos\/videos in your post/i.test(text(element))))
      return stop("Facebook has an unfinished media draft. ClipHarbor kept its attachment and stopped; finish or save that draft before exporting.");
    const files = [...composer.querySelectorAll('input[type=file]')].filter(element=>!element.accept||/video|mp4/i.test(element.accept));
    if(files.length) {
      files[0].setAttribute("data-clipharbor-file",input.marker);
      return {fileSelector:`input[data-clipharbor-file="${input.marker}"]`};
    }
    const photo=findButton(composer,labels.photo);
    if(photo) { photo.click(); return {waiting:"Opening the video attachment area"}; }
    return {waiting:"Waiting for Facebook's video attachment input"};
  }
  if(action === "caption") {
    if(!composer) return {waiting:"Waiting for Facebook's video editor"};
    const box=captionBox(composer);
    if(box) {
      const value=normCaption(box.innerText||box.value||"");
      if(value === normCaption(input.caption||"")) return {captionReady:true};
      if(value) return stop("The composer contains different text. ClipHarbor kept it and stopped.");
      box.focus(); return {insertText:true};
    }
    const next=findButton(composer,labels.next);
    if(next) { next.click(); return {waiting:"Continuing to the caption step"}; }
    return {waiting:"Waiting for the caption field"};
  }
  if(action === "audience") {
    const pattern=labels.audience[input.audience];
    if(!pattern) return stop("Unknown audience.");
    // An audience dialog is distinguished from the main composer, so choosing
    // Friends/Only me never acts on an existing feed post's audience controls.
    const selector=dialogs.find(element=>all(element,'[role=radio],input[type=radio]').length);
    if(selector) {
      const radios=all(selector,'[role=radio],input[type=radio]');
      const choice=radios.find(element=>matches(element,pattern)||pattern.test(accessibleLabel(element))||
        (element.closest('label')&&[element.closest('label'),...element.closest('label').querySelectorAll('span')].some(label=>matches(label,pattern))));
      if(!choice) return stop("The requested audience is unavailable for this Facebook profile. Nothing was posted.");
      if(choice.getAttribute("aria-checked")!=="true" && !choice.checked) { choice.click(); return {waiting:"Selecting the audience"}; }
      for(const checkbox of all(selector,'[role=checkbox],input[type=checkbox]')) {
        if(/default|défaut|predeterminad|ברירת|افتراضي/i.test(text(checkbox)+" "+accessibleLabel(checkbox)) && (checkbox.getAttribute("aria-checked")==="true"||checkbox.checked)) { checkbox.click(); return {waiting:"Keeping your default audience unchanged"}; }
      }
      const done=findButton(selector,labels.done);
      if(done) { done.click(); return {waiting:"Confirming the selected audience"}; }
      return stop("The audience confirmation control was not recognized. Nothing was posted.");
    }
    if(!composer) return {waiting:"Waiting for the audience controls"};
    const current=buttons(composer).find(element=>matches(element,pattern));
    if(current) return {audienceReady:true};
    const audienceControl=buttons(composer).find(element=>Object.values(labels.audience).some(p=>matches(element,p))||/Edit (post )?(audience|privacy)|Select audience|Audience selector/i.test(text(element)));
    if(audienceControl) { audienceControl.click(); return {waiting:"Opening the audience selector"}; }
    const next=findButton(composer,labels.next);
    if(next) { next.click(); return {waiting:"Continuing to post settings"}; }
    return {waiting:"Waiting for a verifiable audience selector"};
  }
  if(action === "publish") {
    if(!composer) return stop("The post composer disappeared before publication.");
    const pattern=labels.audience[input.audience];
    if(!buttons(composer).some(element=>matches(element,pattern))) return stop("The audience changed or could not be verified. Nothing was posted.");
    const box=captionBox(composer);
    if(box && normCaption(box.innerText||box.value||"")!==normCaption(input.caption||"")) return stop("The caption changed before publication. Nothing was posted.");
    const busy=all(composer,'[role=progressbar]').length || /Uploading|Processing video|Mise en ligne|Subiendo/i.test(text(composer));
    if(busy) return {waiting:"Facebook is preparing the video"};
    const post=findButton(composer,labels.post);
    if(!post) return {waiting:"Waiting for the Post button to become available"};
    // The caller records 'posting' with the desktop before this one click.
    for(const element of all(document,'[role=alert],[role=status]')) element.setAttribute("data-clipharbor-before-post",input.marker);
    post.click(); return {clicked:true};
  }
  if(action === "confirm") {
    const announcements=all(document,'[role=alert],[role=status]').filter(element=>element.getAttribute("data-clipharbor-before-post")!==input.marker).map(text).join("\n");
    if(!composer && /(successfully(?: been)?|has been|was) (shared|posted|published)|post (is |was )?(published|shared)|publication.*publiée|publicación.*publicad|פורסם בהצלחה|تم النشر/i.test(announcements)) {
      return {confirmed:true,url:input.profileUrl};
    }
    return {waiting:"Waiting for Facebook to confirm the post"};
  }
  return stop("Unknown Facebook operation.");
}
