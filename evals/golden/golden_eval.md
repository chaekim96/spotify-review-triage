# Golden-50 evaluation

50 hand-labeled reviews vs saved pipeline predictions (missing predictions count as wrong).

| metric | value |
|---|---|
| coverage | 1.0 |
| topic_agreement | 0.42 |
| intent_agreement | 0.8 |
| severity_exact | 0.64 |
| severity_within_1 | 0.94 |
| severity_mae_on_predicted | 0.44 |
| sentiment_mae_on_predicted | 0.294 |
| sentiment_within_0.5 | 0.82 |
| sentiment_within_0.25 | 0.56 |
| needs_review_agreement | 0.82 |
| topic_macro_f1_present_classes | 0.2711 |

Quotes: model 50/50 exact substrings; human 50/50.

## Per-topic

| topic | support | precision | recall | F1 |
|---|---|---|---|---|
| access | 1 | 0.0 | 0.0 | 0.0 |
| usability | 27 | 0.6667 | 0.2222 | 0.3333 |
| playback | 1 | 0.25 | 1.0 | 0.4 |
| downloads | 0 | 0.0 | 0.0 | 0.0 |
| catalog | 0 | 0.0 | 0.0 | 0.0 |
| billing | 0 | 0.0 | 0.0 | 0.0 |
| support | 3 | 0.0 | 0.0 | 0.0 |
| other | 18 | 0.5185 | 0.7778 | 0.6222 |

## Confusion (human -> model)

access->billing: 1, other->catalog: 1, other->other: 14, other->usability: 3, playback->playback: 1, support->billing: 1, support->catalog: 1, support->playback: 1, usability->billing: 2, usability->catalog: 3, usability->downloads: 1, usability->other: 13, usability->playback: 2, usability->usability: 6

## Disagreements

- `292ce26a-815d-4bce-a3b6-93cb6c9e7e2c` fields ['topic', 'severity', 'needs_review']: human support/complaint/sev 5, model catalog/complaint/sev 3. Text: "Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks truth. Spotify is doing all they can to protect pedophiles, by banning Christian songs discussing the path the"
- `a70e8d3e-3f84-46bc-b008-67f476c67963` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Great app use it every chance I get"
- `0d4f8b48-74c1-4e2a-89b5-11eaa737027e` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "It's really an amazing experience with Spotify...I love it🥰"
- `991b6b3a-f511-458a-a5b7-234f78048fb5` fields ['severity']: human usability/complaint/sev 2, model usability/complaint/sev 3. Text: "Ads were okay, but limited functionality..it's just too much"
- `599a0d41-989a-40ef-8ed2-e92db76eea46` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "I just loved it"
- `111f9048-f7bd-4be0-813e-76b8fc49f73f` fields ['topic', 'sentiment']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Excellent"
- `b567f70c-edba-4922-ac2a-e945e5eb3472` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "good ❤❤🔊🔊"
- `b5ee7834-a0eb-4c15-9c7b-935831021922` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Spotify is awesome and and very diverse :)"
- `1fc8b08f-7d6a-472f-b317-8ceb28d00f22` fields ['topic', 'intent']: human access/unclear/sev 1, model billing/praise/sev 1. Text: "Duo Premium .... No ads at all!"
- `947821dc-b356-45dc-a0bc-1903728fad40` fields ['intent']: human playback/request/sev 3, model playback/complaint/sev 3. Text: "Very good but wen I play my song it o ly plays a little bit then it stops I updated my phone and it worked but it happend again they need to fix this issue"
- `723f07de-9881-4049-8680-1a9e25652914` fields ['topic', 'severity', 'sentiment']: human support/complaint/sev 5, model playback/complaint/sev 4. Text: "Update: I reached out to Spotify Support and with some help from Sarah I was able to get the app working again. Old Post:Normally, the app works great, and I use it constantly. I tried to open it toda"
- `47428620-ec21-424d-a515-0b0b0012a5cf` fields ['topic', 'needs_review']: human usability/complaint/sev 2, model other/complaint/sev 2. Text: "This app is bad work"
- `fc344263-308d-48a1-9715-c380d063b6de` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Great..."
- `6112667b-3d71-475c-b1a4-159b87f73d2b` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Super"
- `ac6cd66d-a9d2-42a4-afb8-2f84beff7fd1` fields ['severity', 'needs_review']: human other/unclear/sev 2, model other/unclear/sev 1. Text: "Lhat ng song nasa spotify"
- `44129679-31a0-4108-9314-086a3456f6ae` fields ['severity', 'needs_review']: human other/unclear/sev 2, model other/unclear/sev 1. Text: "Avtar sungh"
- `46842184-32f8-4088-ac15-2a700a7e94ed` fields ['topic', 'intent', 'severity', 'needs_review']: human other/unclear/sev 2, model catalog/complaint/sev 3. Text: "asem, lirik nya kdang gaada kek mana??"
- `657f1b77-0183-4b06-bf48-5e6d9ab08f9a` fields ['topic']: human usability/complaint/sev 2, model other/complaint/sev 2. Text: "Hate This application 👎"
- `5de7f95b-ccad-41b2-9f63-a13f7c1d9f09` fields ['intent', 'severity']: human other/complaint/sev 2, model other/unclear/sev 1. Text: "We are boycotting Swedish app in our protest against Sweden for their desrecpect & desceration of our holy book Qur'an"
- `de48c99b-46fe-4837-8634-e63dbc72a5ea` fields ['topic', 'severity', 'sentiment']: human usability/praise/sev 2, model catalog/praise/sev 1. Text: "I LOVE that I was able to put in only a few songs I like and Spotify gave me recommendations for an AWESOME Playlist...!!!"
- `aa573851-0b86-4b1b-adf6-210268c08d2a` fields ['topic', 'sentiment']: human usability/praise/sev 1, model other/praise/sev 1. Text: "I absolutely love Spotify, to me is one of the best Music Apps. Great job Spotify!!!"
- `372d4e67-59cc-4c54-879f-3e8a202ee554` fields ['topic', 'intent', 'severity', 'sentiment']: human other/unclear/sev 1, model usability/complaint/sev 2. Text: "Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄"
- `47f1406d-4918-4d60-9647-5ca8e610caca` fields ['topic', 'severity']: human usability/complaint/sev 2, model playback/complaint/sev 4. Text: "Very poor updates as we cannot playback the songs and most bad updates are happening it is affecting the spotify quality"
- `82780cbe-6435-4efb-84f6-8e5fa47ffc3a` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "Awesomeness 👌 👏 👍 😍 💖"
- `36609c5c-fe48-4459-86b8-cc78fd3c77cd` fields ['needs_review']: human other/unclear/sev 1, model other/unclear/sev 1. Text: "Bheekhmangon"
- `f4c8146a-d5c8-4168-b00e-21af666afc6a` fields ['needs_review']: human other/unclear/sev 1, model other/unclear/sev 1. Text: "Unconditional love, Stoli Canales"
- `3ddb3f4e-f7b9-430b-b335-eadc6d321f46` fields ['topic', 'intent', 'severity']: human usability/complaint/sev 4, model billing/cancellation/sev 3. Text: "Deleting this App. The new update suck, we can't choose our fvrt songs after some clicks, we can't CHOOSE song after a song played, and we can't turn off shuffle option. They are pushing us to upgrade"
- `16d640e9-b281-4746-9562-c7dbcf7126b6` fields ['topic', 'severity']: human support/complaint/sev 2, model billing/complaint/sev 3. Text: "It's my best music app but now it's not...everything basic features is premium...."
- `8cc4fad4-26ec-47b7-96e8-49c7da714eca` fields ['intent']: human other/unclear/sev 2, model other/complaint/sev 2. Text: "I hate this app and sweden .I love islam"
- `215463ae-95b7-4481-8747-1754b68f31fa` fields ['topic']: human usability/complaint/sev 4, model playback/complaint/sev 4. Text: "What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working. So I unstalled and thn again install it now I can't even open the app.. Just showing try again?? I really lo"
- `46c0b49f-83a1-427e-8f0b-cef62e3c94b5` fields ['severity']: human usability/complaint/sev 5, model usability/complaint/sev 2. Text: "Are you out of your mind? This is dangerous! Listening to music in a normal volume and suddenly an add starts and my ears feel like they explode!! Stop this BS, or you're gonna destroy someones ears."
- `283b5843-a992-464f-b1dc-9dc7281ff390` fields ['intent', 'severity', 'needs_review']: human other/complaint/sev 2, model other/unclear/sev 1. Text: "Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like"
- `1d15724a-98ff-400a-8083-0d9afc801098` fields ['sentiment']: human other/praise/sev 1, model other/praise/sev 1. Text: "Good"
- `89ea724c-358f-48ab-9516-cd130d21c471` fields ['intent', 'sentiment']: human other/unclear/sev 1, model other/praise/sev 1. Text: "Good app!"
- `2aa566c6-b98d-4513-b900-83702a8db8eb` fields ['intent', 'needs_review', 'sentiment']: human usability/complaint/sev 1, model usability/praise/sev 1. Text: "Nice app, very less advertising"
- `8c0546b0-ce43-4a36-9d33-9f979e98d522` fields ['topic', 'severity']: human usability/complaint/sev 4, model catalog/complaint/sev 3. Text: "1-Lyrics not getting loaded, 2-can't go back to or start song where to wanted. Pathetic update"
- `b58dd6f0-ad88-4319-b6db-58afb60c37c1` fields ['severity', 'sentiment']: human usability/request/sev 2, model usability/request/sev 1. Text: "The only thing Spotify lacks is the ability to organize saved \nalbums/artists into collections. Would definitely deserve 5 stars if it \nincluded this feature."
- `dceb14e7-2df0-422f-bb2b-73d7c373159a` fields ['severity']: human usability/complaint/sev 2, model usability/complaint/sev 3. Text: "I gave one star because I can't give any less than that. the new update is sooooooo annoying like I can't even play the songs that I like and I can't rewind songs what the heck"
- `5fba12ea-4980-4f25-a129-f830a3974fd2` fields ['topic']: human usability/praise/sev 1, model catalog/praise/sev 1. Text: "I find Spotify very good, it finds and play whatever music you want and also adds songs that you might like, judging from your playlist if you choose to arrange one. 😊💃🎸🎶"
- `ac4e860a-c042-49cc-90f3-189591c336ac` fields ['topic', 'severity']: human usability/complaint/sev 2, model downloads/complaint/sev 3. Text: "paying for subscribing but unable to play in offline mode really?"
- `9034d675-9582-49b6-a1c1-c4ddabf8baf1` fields ['topic']: human other/complaint/sev 2, model usability/complaint/sev 2. Text: "Worst app ever too much ad"
- `d2f3874f-d15d-4a2f-bb97-4f1213defa46` fields ['topic']: human usability/complaint/sev 2, model billing/complaint/sev 2. Text: "Too expensive and the free version is pretty much unusable with constant ads... Every two or three songs.. Forget it"
- `99b93e31-9f15-4daa-88ac-349ab0419c48` fields ['topic']: human other/complaint/sev 2, model usability/complaint/sev 2. Text: "This update very bad for everyone.old Spotify. we all want."
- `ca63dfbe-7120-4e18-af6e-8ea786cd157d` fields ['topic']: human usability/praise/sev 1, model other/praise/sev 1. Text: "I'm loving the experience with the app"
