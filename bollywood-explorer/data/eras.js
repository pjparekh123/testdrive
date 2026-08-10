// Era definitions — each decade of Hindi cinema gets its own mood, palette and story.
window.ERAS = [
  {
    id: "silent", from: 1913, to: 1930,
    en: "The Silent Dawn", hi: "मूक युग",
    motif: "🎞",
    tag: "Where it all began",
    blurb: "Dadasaheb Phalke cranks a hand-turned camera in Bombay and India falls in love with the moving image. No sound, no colour — just painted backdrops, mythological heroes, and packed tent-theatres. Only a handful of these films survive; each one is a miracle.",
    note: "Box-office records from this era are lost to time — these are the landmark films every lover of Hindi cinema should know."
  },
  {
    id: "1930s", from: 1931, to: 1939,
    en: "The Talkie Revolution", hi: "बोलती फ़िल्में",
    motif: "📻",
    tag: "Alam Ara speaks — and sings",
    blurb: "In 1931 Alam Ara opens at Bombay's Majestic Cinema with seven songs, and Hindi cinema becomes a singing cinema forever. The great studios — Bombay Talkies, New Theatres, Prabhat — rise like film-making gharanas, with salaried stars and in-house poets.",
    note: "Earnings from the studio era are estimates from trade lore; ratings come from IMDb's small but devoted classic-film community."
  },
  {
    id: "1940s", from: 1940, to: 1949,
    en: "Freedom's Soundtrack", hi: "आज़ादी की धुन",
    motif: "🕊",
    tag: "War, Partition, Independence — and box-office history",
    blurb: "As India marches toward freedom, its cinema finds its voice. Kismet runs three straight years in one Calcutta theatre. Partition redraws the industry overnight — Lahore's talent streams into Bombay — and by 1949 the studio system is giving way to the age of stars.",
    note: ""
  },
  {
    id: "1950s", from: 1950, to: 1959,
    en: "The Golden Age", hi: "स्वर्ण युग",
    motif: "✨",
    tag: "Awara, Pyaasa, Mother India — cinema as nation-building",
    blurb: "Nehru's new republic dreams in black and white. Raj Kapoor's tramp charms Moscow, Guru Dutt turns melancholy into poetry, Mehboob Khan puts Mother India on the Oscar shortlist. Songs by Lata, Rafi, Shankar–Jaikishan and S.D. Burman become the republic's true anthems.",
    note: ""
  },
  {
    id: "1960s", from: 1960, to: 1969,
    en: "Technicolor Romance", hi: "रूमानी दौर",
    motif: "🌹",
    tag: "Mughal-e-Azam to Aradhana — colour floods the screen",
    blurb: "Cinema bursts into Eastmancolor: Kashmir houseboats, Shammi Kapoor's yahoo, Sadhana's fringe, Madhubala's Anarkali. Films shoot in Paris and Tokyo, and by decade's end a superstar called Rajesh Khanna is being mobbed by fans who write him letters in blood.",
    note: ""
  },
  {
    id: "1970s", from: 1970, to: 1979,
    en: "Masala & the Angry Young Man", hi: "गुस्सैल जवान",
    motif: "🔥",
    tag: "Sholay, Deewaar, Zanjeer — Amitabh arrives",
    blurb: "The optimism curdles, and cinema answers with fists. Salim–Javed write the Angry Young Man, Amitabh Bachchan becomes a one-man industry, and Sholay runs five years straight at Minerva. Masala is perfected: revenge, lost brothers, cabaret, and R.D. Burman on the soundtrack.",
    note: ""
  },
  {
    id: "1980s", from: 1980, to: 1989,
    en: "Rebels & Disco", hi: "डिस्को दीवाने",
    motif: "🪩",
    tag: "Disco Dancer to Qayamat Se Qayamat Tak",
    blurb: "Video piracy empties the halls, but the decade still glitters: Mithun's disco, Sridevi's comic genius, Mr. India's 'Mogambo khush hua'. And just when the industry seems lost, two debutant Khans — Aamir and Salman — bring romance (and audiences) roaring back.",
    note: ""
  },
  {
    id: "1990s", from: 1990, to: 1999,
    en: "The Romance Renaissance", hi: "प्यार का दशक",
    motif: "🎻",
    tag: "DDLJ, HAHK, KKHH — the Khans rule the world",
    blurb: "Liberalised India falls in love again. Yash Chopra's chiffon, Sooraj Barjatya's weddings, Shah Rukh's outstretched arms in a Swiss meadow. The NRI discovers Bollywood, A.R. Rahman rewires film music, and DDLJ begins a theatrical run that has never ended.",
    note: ""
  },
  {
    id: "2000s", from: 2000, to: 2009,
    en: "Multiplex Bollywood", hi: "मल्टीप्लेक्स युग",
    motif: "🏙",
    tag: "Lagaan to 3 Idiots — Bollywood goes global",
    blurb: "Corporates and multiplexes remake the business. Lagaan reaches the Oscars, Devdas reaches Cannes, and Munna Bhai teaches Gandhigiri. Hrithik debuts like a thunderclap, and by 2009 a film called 3 Idiots is smashing every record in the book.",
    note: ""
  },
  {
    id: "2010s", from: 2010, to: 2019,
    en: "New Bollywood", hi: "नया दौर",
    motif: "🎯",
    tag: "Gangs of Wasseypur to Gully Boy — content is king",
    blurb: "The ₹100-crore club meets the indie wave. Kahaani, Queen and Pink prove stories sell; Dangal earns more in China than any Indian film has anywhere; small-town India takes over from Switzerland as Bollywood's favourite location. Apna time aa gaya.",
    note: ""
  },
  {
    id: "2020s", from: 2020, to: 2025,
    en: "The Streaming Age", hi: "ओटीटी दौर",
    motif: "📡",
    tag: "Pandemic, OTT, and the roar of Pathaan and Jawan",
    blurb: "Theatres go dark in 2020 and premieres move to living rooms. Then the big screen bites back: Pathaan and Jawan detonate at the box office, Animal and Stree 2 rewrite the rulebook, and 12th Fail proves a quiet true story can still make a nation cry.",
    note: "Recent years rank by verified domestic nett collections; ratings are live IMDb scores and may shift."
  }
];

// Films register themselves here, keyed by year.
window.FILMS = {};
// One evocative line of context per year, set by the decade files.
window.YEAR_NOTES = {};
window.registerFilms = function (year, list) {
  window.FILMS[year] = (window.FILMS[year] || []).concat(list);
};
