/* The Silent Dawn · 1913–1930 — landmark films of Indian silent cinema.
   Schema: t title · h Hindi · d director · c cast · m music · r IMDb ·
   er box-office rank that year · bo box-office note · v verdict ·
   w Wikipedia article title · tr trivia · s songs */
(function () {
  const R = window.registerFilms, N = window.YEAR_NOTES;

  N[1913] = "In a rented bungalow in Bombay's Dadar, Dadasaheb Phalke develops film in his bathroom — and a national cinema is born.";
  R(1913, [
    { t: "Raja Harishchandra", h: "राजा हरिश्चंद्र", d: "Dadasaheb Phalke", c: ["Dattatraya Dabke", "Anna Salunke", "Bhalchandra Phalke"], r: 6.4, er: 1, v: "India's first feature film", w: "Raja Harishchandra",
      tr: ["No woman would act in a film in 1913 — so Anna Salunke, a young cook from a Bombay restaurant, played Queen Taramati. Indian cinema's first leading lady was a man.",
        "Phalke sold his wife's jewellery and mortgaged his life insurance to fund the film; his wife Saraswatibai developed the film stock, cooked for the crew, and is arguably India's first film technician.",
        "It premiered at the Coronation Cinema, Girgaon, on 3 May 1913 — a date still celebrated as the birthday of Indian cinema."] },
    { t: "Mohini Bhasmasur", h: "मोहिनी भस्मासुर", d: "Dadasaheb Phalke", c: ["Durgabai Kamat", "Kamlabai Gokhale"], r: 5.9, er: 2, w: "Mohini Bhasmasur",
      tr: ["Durgabai Kamat became the first woman ever to act in Indian cinema, defying ferocious social taboo; her daughter Kamlabai Gokhale, all of 13, became its first child-woman star."] },
  ]);

  N[1917] = "Phalke's mythologicals pack tents so full that special trains are said to bring villagers to see Lanka burn.";
  R(1917, [
    { t: "Lanka Dahan", h: "लंका दहन", d: "Dadasaheb Phalke", c: ["Anna Salunke", "Ganpat Shinde"], r: 6.1, er: 1, v: "First Indian blockbuster", w: "Lanka Dahan",
      tr: ["Anna Salunke played both Ram and Sita — Indian cinema's first double role.",
        "Legend has it coins collected at showings had to be carried away in bullock carts, and audiences prostrated before the screen when Ram appeared."] },
  ]);

  N[1918] = "Phalke launches Hindustan Cinema Films Company — the business of Indian movies begins in earnest.";
  R(1918, [
    { t: "Shri Krishna Janma", h: "श्रीकृष्ण जन्म", d: "Dadasaheb Phalke", c: ["Mandakini Phalke", "D. D. Dabke"], r: 6.0, er: 1, w: "Shri Krishna Janma",
      tr: ["Phalke cast his own seven-year-old daughter Mandakini as baby Krishna; trick photography made gods appear and vanish, astonishing audiences."] },
  ]);

  N[1919] = "Trick photography is now an art: Kaliya Mardan's underwater serpent battle stuns audiences.";
  R(1919, [
    { t: "Kaliya Mardan", h: "कालिया मर्दन", d: "Dadasaheb Phalke", c: ["Mandakini Phalke", "Neelkanth"], r: 6.2, er: 1, w: "Kaliya Mardan",
      tr: ["One of the few Phalke films to survive almost complete; the National Film Archive's restored print still screens today, with Mandakini Phalke's Krishna charming audiences a century on."] },
  ]);

  N[1925] = "European co-productions arrive: Himansu Rai and Franz Osten shoot the Buddha's life with German cameras and Indian light.";
  R(1925, [
    { t: "Prem Sanyas (The Light of Asia)", h: "प्रेम संन्यास", d: "Franz Osten, Himansu Rai", c: ["Himansu Rai", "Seeta Devi"], r: 6.3, er: 1, w: "Prem Sanyas",
      tr: ["An Indo-German co-production on the life of the Buddha that toured Europe; it played a command performance for British royalty at Windsor Castle."] },
  ]);

  N[1928] = "Shiraz builds the Taj Mahal on screen — silent India's most sumptuous romance.";
  R(1928, [
    { t: "Shiraz", h: "शीराज़", d: "Franz Osten", c: ["Himansu Rai", "Enakshi Rama Rau", "Charu Roy", "Seeta Devi"], r: 6.9, er: 1, w: "Shiraz (film)",
      tr: ["A legend of the Taj Mahal, shot entirely on location with jewels lent by maharajas; the BFI's 2017 restoration, with a new score by Anoushka Shankar, brought it back to world screens."] },
  ]);

  N[1929] = "As the silent era peaks, A Throw of Dice fills the screen with elephants, tigers and ten thousand extras.";
  R(1929, [
    { t: "A Throw of Dice (Prapancha Pash)", h: "प्रपंच पाश", d: "Franz Osten", c: ["Seeta Devi", "Himansu Rai", "Charu Roy"], r: 6.8, er: 1, w: "A Throw of Dice",
      tr: ["Filmed with 10,000 extras and 1,000 horses lent by the maharajas of Jaipur, Udaipur and Mysore.",
        "Its Mahabharata-inspired gambling plot was restored by the BFI in 2006 with a score by Nitin Sawhney."] },
    { t: "Gopal Krishna", h: "गोपाल कृष्ण", d: "V. Shantaram", c: ["Suresh Babu", "Kamla Devi"], r: 6.0, er: 2, w: "Gopal Krishna (1929 film)",
      tr: ["The young V. Shantaram's breakthrough at Prabhat Film Company — the studio that would become one of Indian cinema's great houses."] },
  ]);
})();
