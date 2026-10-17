// Injected by harness.py: drives the UI like a user would.
(function () {
  var log = [];
  function check(name, cond, extra) { log.push((cond ? "OK   " : "FAIL ") + name + (extra ? "  " + extra : "")); }
  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function btn(text) { return $all("button").filter(function (b) { return b.textContent.trim() === text; })[0]; }
  function setVal(elm, v) { elm.value = v; elm.dispatchEvent(new Event("input")); elm.dispatchEvent(new Event("change")); }
  function disk(rel) { return JSON.parse(Android.read(rel)); }

  try {
    // 1) Money
    check("ui loaded", !!$("#main .card"), document.getElementById("status").textContent);
    var money = $all("#main input[type=number]");
    setVal(money[0], "5000");
    $all("#main .card")[1].querySelectorAll(".quick button")[1].click();   // Faz-Coins +1000
    $("#saveBtn").click();
    var st = disk("save/state.json");
    check("parts saved", st.Currency.PARTS === 5000, JSON.stringify(st.Currency));
    check("faz-coins +1000", st.Currency.FAZ_TOKENS >= 1000, JSON.stringify(st.Currency));

    // 2) Add an existing mod chip
    show("mods");
    var firstPlus = $all("#main .stepper button")[1];
    firstPlus.click(); firstPlus.click();
    $("#saveBtn").click();
    st = disk("save/state.json");
    check("existing mod added", st.ModInventory.CircleSpeed_Add_01 === 2, JSON.stringify(st.ModInventory));

    // 3) New mod chip
    btn("+ Create a new mod chip").click();
    var inputs = $all("#main .card input"), selects = $all("#main .card select");
    setVal(inputs[0], "Shadow Speed");
    setVal($("#main textarea"), "Stalks very fast");
    setVal(selects[0], "Stalking");            // category
    setVal(selects[1], "StalkingTimeMin");     // effect 1
    setVal(inputs[1], "0.4");
    setVal(selects[2], "StalkingTimeMax");     // effect 2
    setVal(inputs[2], "0.5");
    setVal(selects[3], "3");                   // stars
    setVal(inputs[4], "3");                    // amount
    btn("Create").click();
    var cu = disk("custom/custom.json");
    var mod = cu.mods[cu.mods.length - 1];
    check("new mod written to custom.json", mod && mod.Effects.EffectCategory === "Stalking", JSON.stringify(mod));
    check("version bumped", cu.version === 1, "version=" + cu.version);
    check("name text added", cu.loc.some(function (l) { return l.ID === mod.ModName && l.English === "Shadow Speed"; }));
    st = disk("save/state.json");
    check("new mod in inventory", st.ModInventory[mod.ModLogical] === 3, JSON.stringify(st.ModInventory));
    check("mod shown in list", $("#main").textContent.indexOf("Shadow Speed") >= 0);

    // 4) New skin
    show("skins");
    btn("+ Create a new skin").click();
    setVal($all("#main .card input")[0], "Crimson Freddy");
    setVal($("#main .card select"), "FreddyFazbear");
    btn("Create").click();
    cu = disk("custom/custom.json");
    var suit = cu.plushsuits[cu.plushsuits.length - 1];
    check("new skin written", suit && suit.SkinCategory === "FreddyFazbear" && suit.ArtAssets.Animatronic3D.Bundle === "animatronics/freddy", suit && JSON.stringify(suit.ArtAssets.Animatronic3D));
    st = disk("save/state.json");
    check("skin in inventory", st.Inventory[suit.Logical] && st.Inventory[suit.Logical].PlushSuit === 1);
    check("version 2", cu.version === 2);

    // 5) Toggle an existing skin
    var toggles = $all("#main .switch input");
    var freddy = toggles.filter(function (t) { return t.closest(".card").textContent.indexOf("Freddy Fazbear") === 0; })[0];
    freddy.checked = true; freddy.dispatchEvent(new Event("change"));
    $("#saveBtn").click();
    st = disk("save/state.json");
    check("Freddy skin enabled", st.Inventory.FreddyFazbear && st.Inventory.FreddyFazbear.PlushSuit === 1);

    // 6) Delete custom content
    show("custom");
    check("custom tab lists 2 items", $all("#main .card").length === 2);
    btn("Delete").click();   // first = mod
    cu = disk("custom/custom.json"); st = disk("save/state.json");
    check("mod deleted", cu.mods.length === 0 && !st.ModInventory[mod.ModLogical], "mods=" + cu.mods.length);
    check("mod texts deleted", !cu.loc.some(function (l) { return l.ID.indexOf(mod.ModLogical) >= 0; }));
    check("version 3", cu.version === 3);

    // 7) CPU: add an existing CPU
    show("cpus");
    var toyCard = $all("#main .card").filter(function (c) { return c.textContent.indexOf("Toy Bonnie") === 0; })[0];
    toyCard.querySelectorAll(".stepper button")[1].click();
    $("#saveBtn").click();
    st = disk("save/state.json");
    check("Toy Bonnie CPU added", st.CPUInventory.ToyBonnie === 1, JSON.stringify(st.CPUInventory));

    // 8) Create a new CPU
    btn("+ Create a new CPU").click();
    var cin = $all("#main .card input"), csel = $all("#main .card select");
    setVal(cin[0], "Shadow Toy Bonnie");
    setVal(csel[0], "ToyBonnie");          // base CPU
    setVal(csel[1], "Mangle"); // look
    var chargeInput = cin[1];              // charge chance (%)
    setVal(chargeInput, "60");
    var wildCb = $all("#main .card input[type=checkbox]")[0];
    wildCb.checked = true; wildCb.dispatchEvent(new Event("change"));
    btn("Create").click();
    cu = disk("custom/custom.json"); st = disk("save/state.json");
    var ccpu = cu.cpus[cu.cpus.length - 1], catk = cu.attacks[cu.attacks.length - 1];
    check("custom CPU written", ccpu && ccpu.PlushSuitRef === "Mangle" && ccpu.AttackProfile === ccpu.Logical, ccpu && ccpu.Logical);
    check("custom attack profile", catk && catk.Logical === ccpu.Logical && catk.Pause.NextPhase.Charge.Chance === 0.6
          && catk.Pause.NextPhase.Circle.Chance === 0.4, catk && JSON.stringify(catk.Pause.NextPhase));
    check("wild spawning on", ccpu.SpawnByStreak.RankRangeByBestStreak.Min >= 1, JSON.stringify(ccpu.SpawnByStreak));
    check("custom CPU in inventory", st.CPUInventory[ccpu.Logical] === 1);
    check("custom CPU name", cu.loc.some(function (l) { return l.ID === ccpu.AnimatronicNames.Default && l.English === "Shadow Toy Bonnie"; }));

    // 9) Delete the custom CPU
    show("custom");
    var cpuCard = $all("#main .card").filter(function (c) { return c.textContent.indexOf("Shadow Toy Bonnie") === 0; })[0];
    cpuCard.querySelector("button").click();
    cu = disk("custom/custom.json"); st = disk("save/state.json");
    check("custom CPU deleted", !cu.cpus.length && !cu.attacks.length && !st.CPUInventory[ccpu.Logical]);
  } catch (e) {
    check("exception", false, e && e.stack);
  }
  var pre = document.createElement("pre");
  pre.id = "testout";
  pre.textContent = log.join("\n");
  document.body.appendChild(pre);
})();
