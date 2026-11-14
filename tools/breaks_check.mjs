#!/usr/bin/env node
/* Meal-timed breaks, checked in the real app: plans real drives (OSRM, so it needs the
   internet) in headless Chrome, picks a leaving time on the card, and checks which meals the
   card suggests, when, and where.

       node tools/breaks_check.mjs              # every case, ~2 minutes
       node tools/breaks_check.mjs denver       # only drives whose route contains this

   Not part of check.sh (routing is a network call); run it before and after touching
   breakPicks / breaksCard. Exit code is the number of failing cases. */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find(p => existsSync(p));
const ONLY = (process.argv[2] || '').toLowerCase();
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Same lists as index.html: no breakfast at these, and these are not a meal at all.
const NO_BREAKFAST = ['Popeyes', 'In-N-Out', 'Chipotle', 'Five Guys', 'Shake Shack', "Raising Cane's", 'Wingstop',
  'Olive Garden', 'Texas Roadhouse', "Chili's", "Applebee's", 'Buffalo Wild Wings', 'Red Robin', 'Panda Express',
  'KFC', "Arby's", "Culver's", 'Dairy Queen', "Zaxby's", "Portillo's", 'Cook Out', 'Little Caesars', "Domino's",
  'Pizza Hut', "Jersey Mike's", 'Firehouse Subs', 'Ice cream shop'];
// Open late or all night (index.html LATE): where a break between 10 pm and 6 am should be.
const LATE = ["McDonald's", 'Taco Bell', 'Jack in the Box', "Denny's", 'Waffle House', 'Whataburger', 'IHOP'];
const NOT_A_MEAL = ['Starbucks', "Dunkin'", 'Dutch Bros', "Peet's Coffee", 'Caribou Coffee', 'Krispy Kreme', 'Ice cream shop'];

// "1:05 pm" -> minutes after midnight
const mins = t => { const m = t.match(/(\d+):(\d+) (am|pm)/); return m ? (+m[1] % 12) * 60 + +m[2] + (m[3] === 'pm' ? 720 : 0) : NaN; };
const meals = r => r.stops.filter(s => !/^Break(,|$)/.test(s.label)).map(s => s.label.replace(/, (next day|day \d+)$/, ''));
// Minutes stopped at each suggested stop, as in index.html (DWELL_MEAL / DWELL_BREAK).
const dwell = s => /^Break(,|$)/.test(s.label) ? 20 : 40;
const ZONE_SPLIT = /, (TX|ID|OR|NV|KS|NE|SD|ND|TN|KY|IN|FL|MI)$/;   // states with two time zones
/* Every clock counts the time at the stops before it: between two stops in the same zone on
   the same day, the gap is the driving plus the earlier stop's dwell (clocks are rounded to
   5 minutes, miles to 1). "Dinner 6:00 pm" on LA -> Denver was pure driving time. */
const dwellGaps = r => {
  const bad = [];
  for (let i = 1; i < r.stops.length; i++) {
    const a = r.stops[i - 1], b = r.stops[i];
    if (a.place.slice(-2) !== b.place.slice(-2) || ZONE_SPLIT.test(b.place) || mins(b.clock) < mins(a.clock)) continue;
    const want = (b.mile - a.mile) * r.perMin + dwell(a), got = mins(b.clock) - mins(a.clock);
    if (Math.abs(got - want) > 8) bad.push(`${a.place} -> ${b.place}: ${got} min, want ~${Math.round(want)}`);
  }
  return bad.length ? 'clocks ignore the time at stops: ' + bad.slice(0, 2).join('; ') : '';
};
// The day a stop (or the arrival) is on: 1 the day you leave, 2 the next, then "day 3"...
const dayOf = t => /next day/.test(t) ? 2 : +((t.match(/day (\d+)/) || [])[1] || 1);

/* from, to, leave (minutes after midnight where the drive starts, '' = now), time zone, checks.
   Each check returns '' when fine, or what is wrong. */
const CASES = [
  ['Los Angeles, CA', 'Las Vegas, NV', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast' ? '' : `meals ${meals(r)} (want Breakfast only: arrive before lunch)`,
    // One time zone: arrival is 7:00 + the drive + the time at every stop.
    r => { const want = 420 + r.drive + r.stops.reduce((a, s) => a + dwell(s), 0), got = mins(r.arrive);
      return Math.abs(got - want) <= 6 ? '' : `arrive ${r.arrive}, want ~${Math.floor(want / 60)}:${String(Math.round(want % 60)).padStart(2, '0')} (drive + stops)`; }]],
  ['Los Angeles, CA', 'Las Vegas, NV', 600, 'America/Los_Angeles', [
    r => meals(r).join() === 'Lunch' ? '' : `meals ${meals(r)} (want Lunch only: left after breakfast)`,
    // The leaving time goes into the link, so a shared drive plans the same meals.
    r => /[?&]leave=1000(&|$)/.test(r.url) ? '' : `leaving 10:00 is not in the link: ${r.url}`,
    r => r.opts === 25 + (r.mlabel ? 1 : 0) ? '' : `${r.opts} leaving times offered (want now + all 24 hours)`]],
  // ...and opening that link restores it: 7 am from ?leave=0700, no picking.
  ['Los Angeles, CA', 'Las Vegas, NV', 420, 'America/Los_Angeles', [
    r => r.sel === '420' ? '' : `picker shows "${r.sel}" for ?leave=0700`,
    r => meals(r).join() === 'Breakfast' ? '' : `meals ${meals(r)} from ?leave=0700 (want Breakfast, as when picked)`],
    { link: true }],
  ['Los Angeles, CA', 'Denver, CO', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)}`,
    // Lunch is in Nevada or Utah, at roughly 12:30 LOCAL time
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && /, (NV|UT|AZ)$/.test(l.place) && Math.abs(mins(l.clock) - 750) <= 75 ? '' : `lunch ${l && l.place} ${l && l.clock}`; },
    r => { const d = r.stops.find(s => s.label === 'Dinner'); return d && /, (UT|CO)$/.test(d.place) ? '' : `dinner ${d && d.place}`; },
    // I-70 in Utah has a charger gap: a row in the plan, and no "longest leg" next to it.
    r => r.gap && !/longest leg/.test(r.sub) ? '' : `gap row "${r.gap}", subtitle "${r.sub}"`]],
  // The Texas line jumps an hour at lunchtime: a LATE lunch is fine, an early one is not.
  ['Albuquerque, NM', 'Dallas, TX', 480, 'America/Denver', [
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && mins(l.clock) >= 12 * 60 + 30 - 45 ? '' : `lunch ${l && l.clock}`; }]],
  ['Los Angeles, CA', 'Las Vegas, NV', 720, 'America/Los_Angeles', [
    r => meals(r).join() === '' ? '' : `meals ${meals(r)} (leaving at noon: lunch was had, dinner is in Vegas)`]],
  // Ohio is on Eastern time: lunch near 12:30 THERE, though the drive started on Central time.
  ['Chicago, IL', 'New York, NY', 420, 'America/Chicago', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)}`,
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && Math.abs(mins(l.clock) - 750) <= 45 ? '' : `lunch at ${l && l.clock}`; }]],
  // Planned from a phone in California: "leaving 7 am" is 7 am in Chicago, so breakfast stays.
  ['Chicago, IL', 'New York, NY', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)} (7 am must be Chicago time)`]],
  ['Los Angeles, CA', 'San Diego, CA', '', 'America/Los_Angeles', [
    r => r.title ? '' : 'no card on a short drive']],
  // A short drive with no meal still shows the card: picking a time is how it gets lunch.
  ['Seattle, WA', 'Portland, OR', '', 'America/Los_Angeles', [
    r => r.title ? '' : 'no breaks card']],
  ['Seattle, WA', 'Portland, OR', 600, 'America/Los_Angeles', [
    r => meals(r).join() === 'Lunch' ? '' : `meals ${meals(r)}`]],
  /* The longest charger gap is a row in the plan at its mile (UI-04), and the card does not
     also name a "longest leg", a second "longest" that read as the same thing. */
  ['Denver, CO', 'Salt Lake City, UT', 480, 'America/Denver', [
    r => /^No fast charger for \d+ mi$/.test(r.gap) ? '' : `no charger-gap row (got "${r.gap}")`,
    r => !/longest leg/.test(r.sub) ? '' : `subtitle "${r.sub}" next to the gap row`]],
  // Leaving at 9 pm: breaks between 10 pm and 6 am go to places likely open (BUG-12).
  ['Los Angeles, CA', 'New York, NY', 1260, 'America/Los_Angeles', [
    r => { const night = r.stops.filter(s => s.label === 'Break' && (mins(s.clock) >= 22 * 60 || mins(s.clock) < 6 * 60));
      const bad = night.filter(s => !LATE.includes(s.chain));
      // One may be a 24-hour site with no late chain in walking distance.
      return night.length > 3 && bad.length <= 1 ? '' : `night breaks not at late chains: ${bad.map(s => s.clock + ' ' + s.place + ' (' + s.chain + ')').join(', ')}`; },
    /* Each stop says what is likely open at its clock (stop signals, batch 8): "open late" under
       a night stop at a late chain, "may be closed then" under one that is not, nothing by day. */
    r => { const night = s => mins(s.clock) >= 22 * 60 || mins(s.clock) < 6 * 60;
      const bad = r.stops.filter(s => s.chain && (night(s) ? !s.sig.includes(LATE.includes(s.chain) ? 'late food' : 'food may be closed')
        : /late food|may be closed/.test(s.sig)));
      return r.stops.some(s => night(s) && s.sig.includes('late food')) && !bad.length ? ''
        : `night signals wrong: ${bad.slice(0, 3).map(s => s.clock + ' ' + s.place + ' (' + s.chain + '): "' + s.sig + '"').join(', ') || 'no stop says "late food"'}`; }]],
  /* Coast to coast: more stops than the list renders (LIST_MAX), and every break must still
     open its stop -- 17 of 23 did nothing when the tap looked the stop up by its list row. */
  ['Los Angeles, CA', 'New York, NY', 420, 'America/Los_Angeles', [
    r => r.taps && r.taps.length > 15 ? '' : `only ${r.taps && r.taps.length} breaks to tap`,
    r => { const dead = (r.taps || []).filter(([a, b]) => a !== b); return dead.length ? `${dead.length} break taps did not open their stop: ${JSON.stringify(dead.slice(0, 3))}` : ''; },
    // "Breakfast · Wendy's 4 min" opened a card that led with Panda Express and hid Wendy's in "+14".
    r => { const off = (r.taps || []).filter(([, , k, lead]) => k && !lead.includes(k)); return off.length ? `${off.length} stop cards do not lead with the promised chain: ${JSON.stringify(off.slice(0, 2))}` : ''; },
    // ~41 h of driving from 7 am: the last stops and the arrival are on day 3, not "next day".
    r => dayOf(r.arrive) === 3 ? '' : `arrival "${r.arrive}" (want day 3)`,
    r => r.stops.some(s => s.day === 3) ? '' : 'no stop on day 3',
    r => r.stops.every((s, i) => !i || s.day >= r.stops[i - 1].day) ? '' : 'days go backwards',
    // The day change is marked once, above its first row, not ", next day" on every row.
    r => r.rows.filter(x => x === 'day').length === 2 && r.stops.every(s => !/day/.test(s.label)) ? '' : `day marks: ${r.rows.join(' ')}`],
    { taps: true }],
  /* Planned at night, the default is 8 am the coming morning (not "12:10 am Break, next
     day"), named as such, with "now" first in the picker; the clocks start at 8 and nothing
     is "next day". A drive that is over by 11 pm stays "now"; daytime is unchanged; a link's
     leaving time always wins. `null` leaves the picker alone; `at` is the phone's clock. */
  ['Los Angeles, CA', 'Las Vegas, NV', null, 'America/Los_Angeles', [
    r => r.sel === 'm' && r.mlabel === 'tomorrow 8:00 am' ? '' : `picker "${r.sel}" / "${r.mlabel}" at 10:30 pm (want tomorrow 8:00 am)`,
    r => r.stops.length && r.stops.every(s => mins(s.clock) >= 480 && mins(s.clock) < 14 * 60) ? '' : `clocks ${r.stops.map(s => s.clock)} (want from 8 am)`,
    r => !/day/.test(r.arrive) && mins(r.arrive) > 11 * 60 && mins(r.arrive) < 14 * 60 ? '' : `arrive "${r.arrive}" (want ~12:30 pm, same day)`,
    r => r.rows.every(x => x !== 'day') ? '' : 'a day mark on a morning drive',
    r => !/[?&]leave=/.test(r.url) ? '' : `the night default went into the link: ${r.url}`,
    r => r.opts === 26 && r.first === '' ? '' : `${r.opts} options, first "${r.first}" (want now first, then the morning, then 24 hours)`],
    { at: '2026-11-11T22:30:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', null, 'America/Los_Angeles', [
    r => r.sel === 'm' && r.mlabel === 'this morning 8:00 am' ? '' : `picker "${r.sel}" / "${r.mlabel}" at 1:30 am (want this morning 8:00 am)`,
    r => r.stops.every(s => mins(s.clock) >= 480) && !/day/.test(r.arrive) ? '' : `clocks ${r.stops.map(s => s.clock)} / arrive ${r.arrive}`],
    { at: '2026-11-12T01:30:00-08:00' }],
  // Chicago -> New York planned at 9 pm on a California phone is 11 pm in Chicago: night there.
  ['Chicago, IL', 'New York, NY', null, 'America/Los_Angeles', [
    r => r.sel === 'm' ? '' : `picker "${r.sel}" (want the morning: it is 11 pm where the drive starts)`,
    r => meals(r).join() === 'Lunch,Dinner' ? '' : `meals ${meals(r)} (leaving 8 am: lunch and dinner)`],
    { at: '2026-11-11T21:00:00-08:00' }],
  ['Los Angeles, CA', 'San Diego, CA', null, 'America/Los_Angeles', [
    r => r.sel === '' && !r.mlabel ? '' : `picker "${r.sel}" at 8:30 pm on a 2-hour drive (want now: over by 11 pm)`],
    { at: '2026-11-11T20:30:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', null, 'America/Los_Angeles', [
    r => r.sel === '' && !r.mlabel && r.opts === 25 ? '' : `picker "${r.sel}" / ${r.opts} options at 2 pm (want now, no morning option)`],
    { at: '2026-11-11T14:00:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', 420, 'America/Los_Angeles', [
    r => r.sel === '420' ? '' : `picker "${r.sel}" for ?leave=0700 at 10:30 pm (the link must win)`],
    { at: '2026-11-11T22:30:00-08:00', link: true }],
  /* The route list is the best stop in each ~30-minute stretch (one row per stretch, in
     driving order), with "Show all N stops" below opening every stop and a way back. Breaks
     whose stop is not in the short list still open it. */
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.list && r.list.short > 5 && r.list.short < 20 && r.list.short < r.list.n / 4 ? '' : `short list ${JSON.stringify(r.list)}`,
    r => r.list && r.list.ordered && r.list.oneEach ? '' : `short list not one per stretch in driving order: ${JSON.stringify(r.list && r.list.miles)}`,
    r => r.list && r.list.all === Math.min(r.list.n, 300) && r.list.back === r.list.short ? '' : `show all gave ${r.list && r.list.all} rows of ${r.list && r.list.n}, back to ${r.list && r.list.back}`,
    r => { const dead = (r.taps || []).filter(([a, b]) => a !== b); return r.taps && r.taps.length && !dead.length ? '' : `break taps ${JSON.stringify(r.taps)}`; },
    /* With a car set, the card's tip ("23 min here — time for ...") names the chain the break
       promised: Barstow's "Break · Taco Bell" card said "a coffee run at Starbucks". */
    r => { const t = (r.taps || []).filter(([, , k]) => k); const off = t.filter(([, , k, , tip]) => !tip.includes(k));
      return t.length && t.every(x => x[4]) && !off.length ? '' : `tips that do not name the promised chain: ${JSON.stringify(off.length ? off : t)}`; }],
    { taps: true, list: true, car: 'Tesla Model Y' }],
  /* Share on a drive sends the plan as text: the drive and leaving time, a line per stop
     ("12:30 pm lunch in Primm: Carl's Jr. 3 min from a 350 kW charger"), the arrival, and a
     link -- the drive's /trip/ guide when there is one, else the app with its leaving time --
     marked ref=share. */
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.share && /^LA → Las Vegas · leaving 8:00 am$/.test(r.share.lines[0]) ? '' : `first line "${r.share && r.share.lines[0]}"`,
    r => r.share && r.share.lines.slice(1, -1).length === r.stops.length
      && r.share.lines.slice(1, -1).every((l, i) => l.startsWith(r.stops[i].clock + ' ' + r.stops[i].label.toLowerCase() + ' in ' + r.stops[i].place.split(',')[0] + ': ')
        && / min from a \d+ kW charger$/.test(l)) ? '' : `stop lines ${JSON.stringify(r.share && r.share.lines)} vs ${JSON.stringify(r.stops.map(s => s.clock + ' ' + s.label))}`,
    r => r.share && r.share.lines[r.share.lines.length - 1] === 'arrive ~' + r.arrive.replace(/^arrive ~/, '') ? '' : `last line "${r.share && r.share.lines.slice(-1)}" (card: ${r.arrive})`,
    r => r.share && r.share.url === 'https://chargeandchew.com/trip/los-angeles-to-las-vegas/?ref=share' ? '' : `link ${r.share && r.share.url}`],
    { share: true, at: '2026-11-12T06:00:00-08:00' }],
  /* "Send plan" on the breaks card sends the same. And the link matches the text: the /trip/
     guide plans 8 am with every chain on a day with no usual closures, so any other plan sends
     the app with its own leaving time and day (batch B). */
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.sendBtn === 'Send plan' ? '' : `breaks card button "${r.sendBtn}" (want Send plan)`,
    r => r.share && r.share.url === 'https://chargeandchew.com/trip/los-angeles-to-las-vegas/?ref=share' && r.share.lines.length === r.stops.length + 2 ? '' : `Send plan sent ${JSON.stringify(r.share)}`],
    { share: true, send: true, at: '2026-11-12T06:00:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', 340, 'America/Los_Angeles', [
    r => r.share && /^LA → Las Vegas · leaving 5:40 am$/.test(r.share.lines[0]) ? '' : `first line "${r.share && r.share.lines[0]}"`,
    r => r.share && !/\/trip\//.test(r.share.url) && /[?&]leave=0540(&|$)/.test(r.share.url) && /[?&]ref=share(&|$)/.test(r.share.url) ? '' : `link ${r.share && r.share.url} (want the app leaving 5:40, not the 8 am guide)`],
    { share: true, send: true, link: true, at: '2026-11-12T04:00:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.share && /^LA → Las Vegas · leaving Thu, Nov 26, 8:00 am$/.test(r.share.lines[0]) ? '' : `first line "${r.share && r.share.lines[0]}"`,
    r => r.share && !/\/trip\//.test(r.share.url) && /[?&]day=2026-11-26(&|$)/.test(r.share.url) && /[?&]leave=0800(&|$)/.test(r.share.url) ? '' : `link ${r.share && r.share.url} (want the app on Thanksgiving, not the guide)`],
    { share: true, link: true, extra: '&day=2026-11-26', at: '2026-11-12T06:00:00-08:00' }],
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.share && !/\/trip\//.test(r.share.url) && /[?&]chain=Taco(%20|\+)Bell(&|$)/.test(r.share.url) ? '' : `link ${r.share && r.share.url} (want the app with Taco Bell, not the guide)`],
    { share: true, link: true, extra: '&chain=Taco%20Bell', at: '2026-11-12T06:00:00-08:00' }],
  /* B02: a leaving time already past today is the NEXT one. The trip pages' leave=0800 opened at
     3 pm planned this morning, and Add to calendar put both stops hours in the past. Now: the day
     picker says Tomorrow, the share text says so, and every calendar event is tomorrow's. */
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.day === '2026-11-13' && r.dayText === 'Tomorrow' && r.sel === '480' ? '' : `picker ${r.dayText} (${r.day}) ${r.sel} for leave=0800 at 3 pm (want Tomorrow, 8:00)`,
    r => r.share && /^LA → Las Vegas · leaving tomorrow 8:00 am$/.test(r.share.lines[0]) ? '' : `first line "${r.share && r.share.lines[0]}" at 3 pm`,
    r => { const d = r.cal && r.cal.ics ? r.cal.ics.split('\r\n').filter(l => l.startsWith('DTSTART')) : [];
      return d.length === 2 && d.every(l => /^DTSTART:20261113T/.test(l)) ? '' : `calendar ${JSON.stringify(d)} (want two stops on Nov 13, tomorrow)`; },
    r => r.cal && /day=2026-11-13/.test(r.cal.ics.replace(/\r\n /g, '')) ? '' : 'the calendar link does not carry day=2026-11-13'],
    { link: true, share: true, cal: true, at: '2026-11-12T15:00:00-08:00' }],
  /* A picked day: Thanksgiving. Chick-fil-A (closed on Thanksgiving Day and every Sunday) is never
     a stop then; asked for alone on a Sunday, the plan says why it is empty. */
  ['Atlanta, GA', 'Orlando, FL', 540, 'America/New_York', [
    r => r.day === '2026-11-26' && r.dayText === 'Thanksgiving' ? '' : `picker ${r.dayText} (${r.day}) (want Thanksgiving)`,
    r => r.stops.length >= 2 && r.stops.every(s => s.chain !== 'Chick-fil-A') ? '' : `stops ${r.stops.map(s => s.chain)} on Thanksgiving`,
    r => /[?&]day=2026-11-26(&|$)/.test(r.url) ? '' : `url ${r.url} lost day=`],
    { link: true, extra: '&day=2026-11-26', at: '2026-11-13T09:00:00-05:00' }],
  ['Atlanta, GA', 'Orlando, FL', 540, 'America/New_York', [
    r => r.stops.length >= 2 && r.stops.filter(s => s.chain === 'Chick-fil-A').length >= 2 ? '' : `stops ${r.stops.map(s => s.chain)} (want Chick-fil-A on a Saturday)`],
    { link: true, extra: '&chain=Chick-fil-A&day=2026-11-14', at: '2026-11-13T09:00:00-05:00' }],
  ['Atlanta, GA', 'Orlando, FL', 540, 'America/New_York', [
    r => r.stops.length === 0 && /Chick-fil-A restaurants are closed on Sundays\. No stop for it on Sun, Nov 15\./.test(r.shut) ? '' : `stops ${r.stops.map(s => s.chain)}, note "${r.shut}" (want none, and why, on a Sunday)`],
    { link: true, extra: '&chain=Chick-fil-A&day=2026-11-15', at: '2026-11-13T09:00:00-05:00' }],
  ['Los Angeles, CA', 'Bakersfield, CA', null, 'America/Los_Angeles', [
    r => r.share && /^LA → Bakersfield · leaving tomorrow 8:00 am$/.test(r.share.lines[0]) ? '' : `first line "${r.share && r.share.lines[0]}" at 10:30 pm`,
    r => r.share && /[?&]leave=0800(&|$)/.test(r.share.url) && /[?&]ref=share(&|$)/.test(r.share.url) && /[?&]from=/.test(r.share.url) ? '' : `link ${r.share && r.share.url} (want the app, leaving 8:00, ref=share)`],
    { share: true, at: '2026-11-11T22:30:00-08:00' }],
  /* In the iOS app (the shell's message handler stubbed): Directions from a stop on a planned
     drive asks the shell for a rating; nothing else does (opening stops, a stop off a route).
     About offers "Rate the app" there, and only there. */
  ['Los Angeles, CA', 'Las Vegas, NV', 480, 'America/Los_Angeles', [
    r => r.review && r.review.before.length === 0 && r.review.after.join() === 'review' ? '' : `review asks ${JSON.stringify(r.review)} (want none before Directions, one after)`,
    r => r.review && r.review.offRoute.length === 0 ? '' : `asked for a rating off a route: ${JSON.stringify(r.review && r.review.offRoute)}`,
    r => r.review && r.review.rate === 'https://apps.apple.com/app/id6809134093?action=write-review' && r.review.rateShown ? '' : `Rate the app ${JSON.stringify(r.review)}`],
    { native: true, review: true }],
  ['Los Angeles, CA', 'Las Vegas, NV', 'now', 'America/Los_Angeles', [
    r => r.sel === '' && r.mlabel === 'tomorrow 8:00 am' ? '' : `picker "${r.sel}" for ?leave=now at night (want now, the morning one tap away)`],
    { at: '2026-11-11T22:30:00-08:00', link: true }],
  /* A drive from "Your location" keeps the spot out of the address bar: from=me, which plans
     from wherever you are when the page opens (here: located in LA). A link you send still
     starts where you were. */
  ['me', 'Bakersfield, CA', 480, 'America/Los_Angeles', [
    r => /[?&]from=me(&|$)/.test(r.url) && !/[?&]from=-?\d/.test(r.url) ? '' : `address bar ${r.url} (want from=me, no coordinates)`,
    r => r.sum === 'Your location → Bakersfield, CA' ? '' : `route card "${r.sum}" (want Your location → Bakersfield, CA)`,
    r => r.share && /[?&]from=34\.05\d%2C\+?-118\.24\d(&|$)/.test(r.share.url) && !/[?&]from=me/.test(r.share.url) ? '' : `shared link ${r.share && r.share.url} (want the start's coordinates)`],
    { share: true, me: [34.0522, -118.2437] }],
  /* Add to calendar (batch 9), across a time zone: one event per stop on the card, each starting
     at the card's clock in that stop's own zone (the UTC time and the zone the description names
     agree), lasting the stop's dwell; a stop card on the plan adds just its own stop. */
  ['Los Angeles, CA', 'Denver, CO', 420, 'America/New_York', [
    r => r.cal && r.cal.name === 'charge-and-chew-los-angeles-to-denver.ics' && r.cal.type === 'text/calendar;charset=utf-8' ? '' : `file ${JSON.stringify(r.cal && [r.cal.name, r.cal.type])}`,
    r => { const ev = calEvents(r.cal && r.cal.ics);
      if (ev.length !== r.stops.length) return `${ev.length} events for ${r.stops.length} stops`;
      const bad = ev.filter((e, i) => e.local !== r.stops[i].clock || e.mins !== dwell(r.stops[i]) || !e.summary.startsWith('Charge + ' + r.stops[i].label.toLowerCase() + ': '));
      return bad.length ? 'events off the card: ' + bad.slice(0, 2).map(e => `${e.summary} ${e.start} = ${e.local} (${e.zone}), ${e.mins} min`).join('; ') : ''; },
    r => r.cal && new Set(calEvents(r.cal.ics).map(e => e.zone)).size >= 2 ? '' : 'the drive did not cross a time zone in the events',
    r => r.cal && r.cal.one && calEvents(r.cal.one).length === 1 && calEvents(r.cal.one)[0].local === r.stops[0].clock && r.cal.plan.startsWith(r.stops[0].label + ' ~' + r.stops[0].clock) && /· on your plan/.test(r.cal.plan) ? ''
      : `stop card: ${JSON.stringify(r.cal && [r.cal.plan, r.cal.oneName])}`],
    { cal: true }],
];
/* The events in a .ics: summary, UTC start, minutes, and the local clock it names, checked against
   the UTC time with that zone's offset. */
const ZONE_OFF = { EST: -5, EDT: -4, CST: -6, CDT: -5, MST: -7, MDT: -6, PST: -8, PDT: -7 };
function calEvents(ics) {
  if (!ics) return [];
  const out = [];
  for (const blk of ics.replace(/\r\n /g, '').split('BEGIN:VEVENT').slice(1)) {
    const p = n => (blk.match(new RegExp('\\r\\n' + n + ':([^\\r]*)')) || [])[1] || '';
    const t = v => Date.UTC(+v.slice(0, 4), +v.slice(4, 6) - 1, +v.slice(6, 8), +v.slice(9, 11), +v.slice(11, 13));
    const [, clock, zone] = p('DESCRIPTION').match(/About (\d+:\d\d [ap]m) ([A-Z]{3})/) || [];
    const loc = new Date(t(p('DTSTART')) + (ZONE_OFF[zone] || 0) * 3600e3), h = loc.getUTCHours(), m = loc.getUTCMinutes();
    out.push({ summary: p('SUMMARY').replace(/\\,/g, ','), start: p('DTSTART'), zone, said: clock, mins: (t(p('DTEND')) - t(p('DTSTART'))) / 6e4,
      local: zone in ZONE_OFF && clock === `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}` ? clock : `UTC ${p('DTSTART')} is not ${clock} ${zone}` });
  }
  return out;
}
// Every case: stops in time order (within a zone this is plain order), a meal at a meal place.
const ALWAYS = [
  r => r.stops.every(s => s.label !== 'Breakfast' || !NO_BREAKFAST.includes(s.chain)) ? '' : 'breakfast at a place with no breakfast',
  r => r.stops.every(s => !/^(Lunch|Dinner)/.test(s.label) || !NOT_A_MEAL.includes(s.chain)) ? '' : 'lunch or dinner at a coffee/ice cream place',
  r => r.stops.every((s, i) => !i || s.mile > r.stops[i - 1].mile) ? '' : 'stops out of order',
  dwellGaps,
  // A break is never within ~1.5 h of driving after the stop before (BUG-11: Childress, then
  // Vernon an hour later).
  r => { const bad = r.stops.filter((s, i) => s.label === 'Break' && (s.mile - (i ? r.stops[i - 1].mile : 0)) * r.perMin < 150 * 0.6 - 3);
    return bad.length ? 'breaks bunched up: ' + bad.map(s => s.clock + ' ' + s.place).join(', ') : ''; },
];

async function cdpConnect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pending = new Map();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  return { send, close: () => ws.close() };
}
function startServer() {
  return new Promise((res, rej) => {
    const p = spawn('python3', ['-u', '-m', 'http.server', '0', '--bind', '127.0.0.1'], { cwd: ROOT });
    const hit = d => { const m = String(d).match(/port (\d+)/); if (m) res({ p, port: +m[1] }); };
    p.stdout.on('data', hit); p.stderr.on('data', hit);
    setTimeout(() => rej(new Error('server did not start')), 8000);
  });
}
async function startChrome(profile) {
  const p = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', '--window-size=420,900',
    // overpass-api.de has banned this machine: no run may reach it (NXDOMAIN).
    '--host-resolver-rules=MAP *overpass* ~NOTFOUND, MAP overpass-api.de ~NOTFOUND', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const ws = await new Promise((res, rej) => {
    p.stderr.on('data', d => { const m = String(d).match(/DevTools listening on (ws:\/\/\S+)/); if (m) res(m[1]); });
    setTimeout(() => rej(new Error('chrome did not start')), 15000);
  });
  return { p, ws };
}

const READ = `(() => {
  const card = document.querySelector('.breaks');
  if (!card) return null;
  return { title: card.querySelector('.bh').firstChild.textContent.trim(),
    arrive: (card.querySelector('.bleave > span:last-child') || {}).textContent || '',
    // The departure day (B02): the day picker beside the hour, and the note when a chain is shut that day.
    day: (document.getElementById('leaveDaySel') || {}).value, dayText: ((document.querySelector('#leaveDaySel option:checked') || {}).textContent || ''),
    shut: (card.querySelector('.bshut') || {}).textContent || '',
    url: location.search, sum: (document.querySelector('#routeInfo .sum b') || {}).textContent || '', sel: document.getElementById('leaveSel').value, opts: document.getElementById('leaveSel').options.length,
    first: document.getElementById('leaveSel').options[0].value,
    mlabel: (document.querySelector('#leaveSel option[value="m"]') || {}).textContent || '',
    // "1,018 mi · 15h 02m": the drive in minutes, and minutes per mile
    ...(() => { const t = (document.querySelector('#routeInfo .sum i') || {}).textContent || '';
      const mi = +((t.match(/([\\d,]+) mi/) || [])[1] || '0').replace(/,/g, '');
      const h = t.match(/(\\d+)h(?: (\\d+)m)?/), m = t.match(/· (\\d+) min/);
      const drive = h ? +h[1] * 60 + +(h[2] || 0) : m ? +m[1] : 0;
      return { drive, perMin: mi ? drive / mi : 0 }; })(),
    sub: (card.querySelector('.bh small') || {}).textContent || '',
    gap: (card.querySelector('.brk.gap .bt b') || {}).textContent || '',
    rows: [...card.children].filter(e => e.matches('.brk, .bday')).map(e => e.matches('.bday') ? 'day' : e.matches('.gap') ? 'gap' : 'stop'),
    stops: (() => {
      // A row per stop; each day after the first starts under a "Next day · ..." / "Day 3 · ..." line.
      let day = 1; const out = [];
      for (const b of card.children) {
        if (b.matches('.bday')) { day = /^Next day/.test(b.textContent) ? 2 : +(b.textContent.match(/^Day (\\d+)/) || [])[1]; continue; }
        if (!b.matches('.brk[data-brk]')) continue;
        const line = b.querySelector('.bt span').textContent;
        // "350 kW · 🍔 Wendy's 4 min": the part ending in "min", without its emoji
        const seg = line.split(' · ').find(x => / \\d+ min$/.test(x)) || '';
        const chain = seg.replace(/^\\S+ /, '').replace(/ \\d+ min$/, '');
        out.push({ clock: b.querySelector('.bm').firstChild.textContent.trim(), label: b.querySelector('.bm i').textContent, day,
          place: b.querySelector('.bt b').textContent, chain, mile: +(b.querySelector('.bm small').textContent.match(/mile (\\d+)/) || [])[1],
          sig: (b.querySelector('.bt .bs') || {}).textContent || '' });
      }
      return out; })() };
})()`;

// Tap Share with the system share sheet stubbed: what it would send.
const SHARE = `(async () => {
  let got = null;
  navigator.share = async d => { got = d; };
  const w = window.innerWidth; Object.defineProperty(window, 'innerWidth', { value: 400, configurable: true });
  const sb = window.__SEND && document.querySelector('.breaks .bcal [data-send]');
  window.__sendBtn = sb ? sb.textContent.trim() : null;
  (sb || document.getElementById('shareBtn')).click();
  await new Promise(r => setTimeout(r, 300));
  Object.defineProperty(window, 'innerWidth', { value: w, configurable: true });
  return got && { lines: (got.text || '').split('\\n'), url: got.url, btn: window.__sendBtn };
})()`;
// Open a stop, then tap its Directions; then the same off the route. Messages the shell got.
const REVIEW = `(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const asks = () => window.__ccMsgs.filter(m => m.cmd === 'review').map(m => m.cmd);
  const openDir = async () => {
    for (let i = 0; i < 40 && !document.querySelector('.leaflet-popup-content .pp-links a[href*="/maps/dir/"]'); i++) await wait(100);
    const a = document.querySelector('.leaflet-popup-content .pp-links a[href*="/maps/dir/"]');
    if (a) { a.addEventListener('click', e => e.preventDefault(), { once: true }); a.click(); }
    await wait(200);
  };
  document.querySelector('#list .row .rowname').click();
  await wait(1200);
  const before = asks();
  await openDir();
  const after = asks();
  window.__ccMsgs.length = 0;
  document.getElementById('rClear').click();
  await wait(600);
  document.querySelector('#list .row .rowname').click();
  await wait(1200);
  await openDir();
  const rate = document.getElementById('rateApp');
  return { before, after, offRoute: asks(), rate: rate && rate.href, rateShown: !!(rate && rate.closest('.app-only') && getComputedStyle(rate.closest('.app-only')).display !== 'none') };
})()`;
// The route list: short (one per stretch), then all, then short again.
const LIST = `(async () => {
  const rows = () => [...document.querySelectorAll('#list .row')];
  const miles = rows().map(r => +(r.querySelector('.idx b') || {}).textContent);
  const span = 30 * (+((document.querySelector('#routeInfo .sum i') || {}).textContent.match(/([\\d,]+) mi/) || [])[1].replace(/,/g, '')) /
    ((t => { const h = t.match(/(\\d+)h(?: (\\d+)m)?/); return h ? +h[1] * 60 + +(h[2] || 0) : 60; })((document.querySelector('#routeInfo .sum i') || {}).textContent || ''));
  const buckets = miles.map(m => Math.floor(m / Math.max(10, span)));
  const out = { n: +document.getElementById('sheetTitle').textContent.replace(/,/g, '').match(/\\d+/)[0], short: miles.length, miles,
    ordered: miles.every((m, i) => !i || m >= miles[i - 1]), oneEach: new Set(buckets).size === buckets.length };
  const all = document.getElementById('routeAll');
  if (!all) return out;
  all.click(); await new Promise(r => setTimeout(r, 300));
  out.all = rows().length;
  const back = document.getElementById('routeBest'); if (back) back.click();
  await new Promise(r => setTimeout(r, 300));
  out.back = rows().length;
  return out;
})()`;
// Add to calendar: the file the card's button saves, then a stop card's own button.
const CAL = `(async () => {
  const blobs = []; URL.createObjectURL = b => { blobs.push(b); return 'blob:x'; }; URL.revokeObjectURL = () => {};
  let name = null; HTMLAnchorElement.prototype.click = function () { name = this.download; };
  document.querySelector('.calbtn[data-cal]').click();
  const out = { name, type: blobs[0] && blobs[0].type, ics: blobs[0] && await blobs[0].text() };
  document.querySelector('.brk[data-brk]').click();
  for (let i = 0; i < 40 && !document.querySelector('.leaflet-popup-content .pp-cal'); i++) await new Promise(r => setTimeout(r, 100));
  const pc = document.querySelector('.leaflet-popup-content .pp-cal');
  out.plan = pc ? pc.parentNode.textContent : '';
  if (pc) { pc.click(); out.oneName = name; out.one = blobs[1] && await blobs[1].text(); }
  return out;
})()`;
// Tap every break in turn; each must open the stop card at the break's own mile, its first
// place being the chain the break promised.
const TAPS = `(async () => {
  const out = [];
  for (const b of [...document.querySelectorAll('.brk[data-brk]')]) {
    const want = +(b.textContent.match(/mile (\\d+)/) || [])[1];
    b.click();
    let got = null;
    for (let i = 0; i < 30 && got !== want; i++) {
      await new Promise(r => setTimeout(r, 100));
      const pm = document.querySelector('.leaflet-popup-content .pp-mile');
      got = pm ? +(pm.textContent.match(/mile (\\d+)/) || [])[1] : null;
    }
    const lead = document.querySelector('.leaflet-popup-content .pp-nb');
    const tip = document.querySelector('.leaflet-popup-content .pp-dwell');
    out.push([want, got, b.dataset.k || '', lead ? lead.textContent : '', tip ? tip.textContent.replace(/\\s+/g, ' ').trim() : '']);
  }
  return out;
})()`;

async function main() {
  if (!CHROME) { console.log('SKIP: Chrome not found'); return 0; }
  const { p: srv, port } = await startServer();
  const profile = mkdtempSync(join(tmpdir(), 'cc-breaks-'));
  const { p: chrome, ws } = await startChrome(profile);
  const B = await cdpConnect(ws);
  let fails = 0;
  for (const [from, to, leave, tz, checks, opt] of CASES) {
    if (ONLY && !(from + ' ' + to).toLowerCase().includes(ONLY)) continue;
    const tag = `${from} -> ${to}, leaving ${leave === '' || leave === 'now' ? 'now' : leave === null ? 'default' : Math.floor(leave / 60) + ':' + String(leave % 60).padStart(2, '0')}${opt && opt.at ? ' (planned ' + opt.at.slice(5, 16) + ')' : ''}`;
    const { targetId } = await B.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId: S } = await B.send('Target.attachToTarget', { targetId, flatten: true });
    const send = (m, p) => B.send(m, p, S);
    const ev = async expr => {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };
    let why = [], res = null;
    try {
      await send('Page.enable'); await send('Runtime.enable');
      await send('Emulation.setTimezoneOverride', { timezoneId: tz });
      await send('Emulation.setFocusEmulationEnabled', { enabled: true });
      if (opt && opt.me) {
        await B.send('Browser.grantPermissions', { permissions: ['geolocation'] });
        await send('Emulation.setGeolocationOverride', { latitude: opt.me[0], longitude: opt.me[1], accuracy: 30 });
      }
      // The iOS shell: a message handler the page can post to, keeping what it is sent.
      if (opt && opt.native) await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__ccMsgs = [];
        window.webkit = { messageHandlers: { cc: { postMessage: m => window.__ccMsgs.push(m) } } };` });
      if (opt && opt.car) await send('Page.addScriptToEvaluateOnNewDocument', { source: `try { localStorage.setItem('cc_car', ${JSON.stringify(opt.car)}); } catch (e) {}` });
      // The phone's clock, moved to `at` (the app reads Date.now() and new Date()).
      if (opt && opt.at) await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
        const RD = Date, off = RD.parse(${JSON.stringify(opt.at)}) - RD.now();
        class D extends RD { constructor(...a) { if (a.length) super(...a); else super(RD.now() + off); } static now() { return RD.now() + off; } }
        window.Date = D; })();` });
      const lv = opt && opt.link ? (leave === 'now' ? '&leave=now' : `&leave=${String(Math.floor(leave / 60)).padStart(2, '0')}${String(leave % 60).padStart(2, '0')}`) : '';
      await send('Page.navigate', { url: `http://127.0.0.1:${port}/?nosw=1&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}${lv}${(opt && opt.extra) || ''}` });
      for (let i = 0; i < 120; i++) { await sleep(500); if (await ev(`!!document.getElementById('leaveSel')`)) break; }
      if (!lv && leave !== null) await ev(`(() => { const s = document.getElementById('leaveSel'); if (!s) return; s.value = ${JSON.stringify(String(leave))}; s.dispatchEvent(new Event('change')); })()`);
      await sleep(400);
      res = await ev(READ);
      if (res && opt && opt.list) res.list = await ev(LIST);
      if (res && opt && opt.share) { if (opt.send) await ev('window.__SEND = 1'); res.share = await ev(SHARE); res.sendBtn = res.share && res.share.btn; }
      if (res && opt && opt.review) res.review = await ev(REVIEW);
      if (res && opt && opt.taps) res.taps = await ev(TAPS);
      if (res && opt && opt.cal) res.cal = await ev(CAL);
      if (!res) why.push('no breaks card (route did not load?)');
      else for (const c of [...checks, ...ALWAYS]) { const w = c(res); if (w) why.push(w); }
    } catch (e) { why.push('error: ' + e.message); }
    await B.send('Target.closeTarget', { targetId });
    if (why.length) { fails++; console.log(`FAIL  ${tag}\n        ${why.join('; ')}`); }
    else console.log(`ok    ${tag}`);
    if (res) console.log('        ' + res.stops.map(s => `${s.clock} ${s.label} ${s.place} (${s.chain})`).join(' | '));
  }
  B.close(); chrome.kill(); srv.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  console.log(`\nbreaks check: ${fails ? fails + ' failing' : 'all pass'}`);
  return fails;
}
main().then(n => process.exit(n), e => { console.error(e); process.exit(99); });
