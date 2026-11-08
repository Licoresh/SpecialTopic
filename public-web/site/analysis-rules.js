const entities = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', ndash: '–', mdash: '—', bull: '•'};
const missing = new Set(['', 'n/a', 'na', 'none', 'null', 'nil', 'unknown', 'not stated', 'not specified', 'unspecified', 'not available', 'not provided', 'not applicable', 'no info', 'no information', '-', '—']);
const EXTRA_SKILLS = {
  'Technical / Digital': 'aws;azure;gcp;mysql;postgresql;mongodb;pyspark;apache spark;apache airflow;apache hadoop;snowflake;databricks;pandas;numpy;scikit-learn;pytorch;tensorflow;typescript;etl;agile scrum;prompt engineering',
  'Soft / Enabling': 'communication;learning and application;attention to detail',
};
const EXTRA_ALIASES = {
  'cloud compute': 'cloud computing', 'datum governance': 'data governance', 'amazon web services': 'aws',
  'microsoft azure': 'azure', 'google cloud platform': 'gcp', 'willingness to learn': 'learning and application',
  'ability to communicate': 'communication', 'data visualisation': 'data visualization',
};
const textFields = ['job_description', 'required_skills', 'preferred_skills', 'qualifications'];
const numberWords = Object.fromEntries('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(' ').map((word, index) => [word, index]));
const numberToken = `(?:[0-9]+(?:\\.[0-9]+)?|${Object.keys(numberWords).sort((a, b) => b.length - a.length).join('|')})`;
const durationPattern = new RegExp(`(?<![\\w.])(?:between\\s+(?<betweenLow>${numberToken})\\s+and\\s+(?<betweenHigh>${numberToken})|(?<low>${numberToken})(?:\\s*(?:[-–—]|to)\\s*(?<high>${numberToken}))?)\\s*(?<plus>\\+)?\\s*(?:years?|yrs?)\\b`, 'gi');
const ambiguousDurationPrefix = new RegExp(`(?:[-−]\\s*|\\b${numberToken}\\s+or\\s*)$`, 'i');
const noExperience = /\bno\s+(?:(?:prior|previous|work|professional)\s+)*experience\s+(?:is\s+)?(?:required|necessary|needed)\b/i;
const experienceContext = /\b(?:experience|experienced|employment|worked|working|career|tenure|professional background|work history)\b|\b(?:years?|yrs?)\s+(?:as\s+|of\s+(?:this\s+)?(?:job|role|position|profession|industry|field)|in\s+(?:the\s+)?(?:same\s+|related\s+|relevant\s+)?(?:job|role|position|field|industry))\b/i;
const schoolDuration = /^(?:\s+|\s*['’]\s*)(?:of|in)\s+(?:an?\s+|the\s+)?(?:college|university|school|education|degree|course|study|undergraduate|graduate|vocational|shs|senior high)\b|^\s+old\b/i;
const employerHistory = /\b(?:we|our company|the company|the firm|the organization)\s+(?:have|has|bring|brings|boast|boasts)\s*$/i;
const occupations = /\b(?:analysts?|scientists?|engineers?|developers?|specialists?|officers?|assistants?|consultants?|architects?|designers?|managers?|coordinators?|administrators?|owners?|recruiters?|trainers?|instructors?|teachers?|auditors?|technicians?|operators?|executives?|directors?|statisticians?)\b/g;
const broadLocations = new Set(['philippines', 'ph', 'phl', 'remote', 'work from home', 'wfh', 'hybrid', 'onsite', 'on-site']);
const escapeRegExp = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const termPattern = (terms, flags) => new RegExp(`(?<![\\p{L}\\p{N}_+#])(?:${terms.map(escapeRegExp).join('|')})(?![\\p{L}\\p{N}_+#])`, flags);

function plain(value, preserveLines = false) {
  const decoded = String(value ?? '').replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (raw, entity) => {
    const key = entity.toLowerCase();
    if (Object.hasOwn(entities, key)) return entities[key];
    if (!key.startsWith('#')) return raw;
    const point = key.startsWith('#x') ? parseInt(key.slice(2), 16) : Number(key.slice(1));
    return point > 0 && point <= 0x10ffff ? String.fromCodePoint(point) : ' ';
  }).normalize('NFKC');
  return decoded.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
    .replace(/<\s*\/?\s*(?:br|p|li|ul|ol|div|tr|h[1-6])\b[^>]*>/gi, preserveLines ? '\n' : ' ')
    .replace(/<\/?[a-z][^<>]*>/gi, ' ').replace(preserveLines ? /[^\S\r\n]+/g : /\s+/g, ' ').trim();
}

export const normalize = value => plain(value).toLowerCase();
export const isMissing = value => missing.has(normalize(value));

function requirementText(value) {
  const lines = plain(value, true).split(/[\r\n•▪◦●]+/);
  let skip = false;
  return lines.filter(line => {
    if (/^\s*(?:requirements?|qualifications?|about the role|responsibilities|duties|your role|what you(?:'ll| will) do|skills|what you bring)\s*[:\-–—]?/i.test(line)) skip = false;
    if (/^\s*(?:about (?:us|the company)|our benefits|benefits|perks|what we offer|why join us|equal opportunity)\s*(?:[:\-–—]|$)/i.test(line)) skip = true;
    return !skip && !/^\s*(?:we are an equal opportunity employer|all qualified applicants|protected by applicable)/i.test(line);
  }).join('\n').replace(/\bhttps?:\/\/[^\s]+/gi, ' ');
}

function titleGrouping(value, aliases, rules) {
  const title = normalize(value).replace(/^\s*[a-z]{2,6}\d{4,}\s*[-–—:]\s*/i, '').trim();
  if (missing.has(title) || title.length > 240) return '';
  function occupation(part) {
    if (Object.hasOwn(aliases, part)) return aliases[part];
    if ((part.match(occupations) ?? []).length !== 1 || /\b(?:manager|recruiter|trainer|instructor|teacher|owner|director|head)\b/.test(part)) return '';
    const matches = rules.filter(([, rule]) => rule.test(part));
    return matches.length === 1 ? matches[0][0] : '';
  }
  const parts = title.split(/\s*\/\s*/).filter(Boolean);
  const groups = new Set(parts.map(occupation));
  return groups.size === 1 && !groups.has('') ? [...groups][0] : title;
}

function locationGrouping(value, regions, cities) {
  const text = normalize(value);
  if (missing.has(text)) return {region: '', city: '', status: 'Not stated'};
  const places = new Set(), selectedRegions = new Set();
  for (const rawPart of text.replace(/\((?:remote|hybrid|onsite|on-site|work from home)\)/g, '').split(/[,;/|]/)) {
    const part = rawPart.trim();
    if (!part || broadLocations.has(part)) continue;
    if (Object.hasOwn(cities, part)) {
      const [region, city] = cities[part];
      selectedRegions.add(region);
      places.add(city);
    } else if (Object.hasOwn(regions, part)) selectedRegions.add(regions[part]);
    else return {region: '', city: '', status: 'Needs review'};
  }
  if (selectedRegions.size > 1 || places.size > 1) return {region: '', city: '', status: 'Multiple or conflicting locations'};
  const [region = ''] = selectedRegions;
  return {region, city: [...places][0] ?? '', status: region ? 'Classified' : 'Broad or remote location'};
}

function educationLevel(job, rules) {
  const explicit = normalize(job.education_requirement);
  const hasField = !missing.has(explicit) && !/^(?:education(?:al)?\s+)?(?:level\s+)?not\s+specified$/.test(explicit);
  const qualifications = normalize(job.qualifications);
  const text = hasField ? explicit : qualifications;
  let levels = rules.filter(([, rule]) => rule.test(text)).map(([name]) => name);
  if (levels.includes('senior high school')) levels = levels.filter(level => level !== 'high school');
  levels = [...new Set(levels.map(level => ["bachelor's degree", 'undergraduate / college level'].includes(level) ? 'college / undergraduate' : level))];
  const stated = hasField || levels.length > 0;
  if (levels.length !== 1 || /\b(?:preferred|preferably|optional|not required|no degree|equivalent experience)\b/.test(text)) {
    return {label: '', status: stated ? 'Needs review' : 'Not stated', source: hasField ? 'education_requirement' : stated ? 'qualifications' : ''};
  }
  return {label: levels[0], status: 'Classified', source: hasField ? 'education_requirement' : 'qualifications'};
}

function experienceDurations(job, texts) {
  const explicit = !isMissing(job.experience_requirement);
  const sources = explicit ? ['experience_requirement'] : textFields;
  const durations = new Map();
  for (const field of sources) {
    const text = explicit ? plain(job[field], true) : texts[field];
    if (!/\b(?:years?|yrs?|experience)\b/i.test(text)) continue;
    for (const clause of text.split(/[\r\n;]+|(?<=[.!?])\s+/)) {
      if (noExperience.test(clause)) durations.set('no experience required', {label: 'no experience required', wording: clause.trim(), field});
      for (const match of clause.matchAll(durationPattern)) {
        const left = clause.slice(Math.max(0, match.index - 90), match.index);
        const right = clause.slice(match.index + match[0].length, match.index + match[0].length + 90);
        if (schoolDuration.test(right) || employerHistory.test(left) || /^\s+of experience\s*,\s*(?:we|our)\b/i.test(right)) continue;
        if (!explicit && !experienceContext.test(`${left}${match[0]}${right}`)) continue;
        if (ambiguousDurationPrefix.test(left) || /^\s+(?:or\s+\d|and\s+\d)/i.test(right)) continue;
        const year = token => numberWords[token.toLowerCase()] ?? Number(token);
        const low = year(match.groups.low ?? match.groups.betweenLow);
        const highToken = match.groups.high ?? match.groups.betweenHigh;
        const min = match.groups.plus || /\b(?:at least|minimum(?: of)?|min\.?)\s*$/i.test(left) || /^\s*(?:\+|or more\b|or above\b)/i.test(right);
        const max = /\b(?:up to|at most|maximum(?: of)?|max\.?)\s*$/i.test(left);
        const more = /\b(?:more than|over)\s*$/i.test(left);
        const less = /\b(?:less than|under)\s*$/i.test(left);
        const qualifiers = [min, max, more, less].filter(Boolean).length;
        const high = highToken ? year(highToken) : null;
        if (low > 100 || qualifiers > 1 || (high !== null && (high > 100 || high < low || qualifiers))) continue;
        const years = `${low} ${low === 1 ? 'year' : 'years'}`;
        const label = high !== null ? `${low}–${high} years` : min ? `at least ${years}` : max ? `up to ${years}`
          : more ? `more than ${years}` : less ? `less than ${years}` : `${years} stated`;
        if (!durations.has(label)) durations.set(label, {label, wording: clause.trim(), field});
      }
    }
  }
  return {durations: [...durations.values()], status: durations.size ? 'Parsed' : explicit ? 'Needs review' : 'No duration identified'};
}

function postingMonth(value) {
  const date = plain(value);
  const iso = date.match(/^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?(?=$|T\d| \d)/);
  const checked = (year, month, day = 1) => {
    if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || new Date(Date.UTC(year, month - 1, day)).getUTCMonth() !== month - 1) return '';
    return `${year}-${String(month).padStart(2, '0')}`;
  };
  if (iso) return checked(Number(iso[1]), Number(iso[2]), iso[3] === undefined ? 1 : Number(iso[3]));
  const numeric = date.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (numeric) {
    const [, first, second, year] = numeric.map(Number);
    if (first <= 12 && second <= 12 && first !== second) return '';
    return checked(year, first > 12 ? second : first, first > 12 ? first : second);
  }
  if (!/\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b/i.test(date) || !/\b\d{4}\b/.test(date)) return '';
  const parsed = new Date(date);
  return Number.isFinite(+parsed) ? checked(parsed.getUTCFullYear(), parsed.getUTCMonth() + 1, parsed.getUTCDate()) : '';
}

export function prepareRules(reference) {
  const categories = new Map();
  for (const [category, terms] of Object.entries(reference.skills)) {
    for (const term of [...terms, ...(EXTRA_SKILLS[category]?.split(';') ?? [])]) categories.set(normalize(term), category);
  }
  const aliases = new Map(Object.entries({...reference.skillAliases, ...EXTRA_ALIASES}));
  const canonical = term => aliases.get(normalize(term)) ?? normalize(term);
  for (const [term, category] of [...categories]) categories.set(canonical(term), category);
  const skillTerms = new Set([...categories.keys(), ...aliases.keys()]);
  const direct = new Map();
  for (const item of reference.competencies) {
    const terms = [item.competency_name, ...item.aliases.split(';'), ...item.keywords.split(';')];
    for (const raw of terms) {
      const term = normalize(raw);
      if (!term || term.length < 3) continue;
      skillTerms.add(term);
      const label = canonical(term);
      if (!direct.has(label)) direct.set(label, new Set());
      direct.get(label).add(item);
      if (!categories.has(label)) categories.set(label, /^enabling/i.test(item.competency_category) ? 'Soft / Enabling' : 'Framework functional skill');
    }
  }
  const byCanonical = new Map();
  for (const term of skillTerms) {
    const label = canonical(term);
    if (!byCanonical.has(label)) byCanonical.set(label, []);
    byCanonical.get(label).push(term);
  }
  const links = new Map();
  const profileTexts = reference.competencies.map(item => ({item, range: normalize(item.range_of_application), description: normalize(item.competency_description)}));
  for (const [label, alternatives] of byCanonical) {
    if (direct.has(label)) {
      links.set(label, [...direct.get(label)].map(item => ({item, method: 'Competency name or alias'})));
      continue;
    }
    const usable = alternatives.filter(term => term.length >= 2);
    if (label === 'statistics') usable.push('statistical');
    if (!usable.length && label !== 'r') continue;
    const pattern = usable.length ? termPattern(usable, 'iu') : null;
    const matched = [];
    for (const {item, range, description} of profileTexts) {
      const rInRange = label === 'r' && /(?:^|[•;,])\s*R\s*(?=$|[•;,])|\bR (?:programming|language)\b/.test(item.range_of_application);
      if (rInRange || pattern?.test(range)) matched.push({item, method: 'Range of Application'});
      else if (pattern?.test(description)) matched.push({item, method: 'Competency description'});
    }
    if (matched.length) links.set(label, matched);
  }
  const matcher = termPattern([...skillTerms].sort((a, b) => b.length - a.length), 'giu');
  const titleRules = Object.entries(reference.titleRules).map(([name, pattern]) => [name, new RegExp(pattern, 'i')]);
  const educationRules = reference.educationLevels.map(([name, pattern]) => [name, new RegExp(pattern, 'i')]);
  return {
    job(job) {
      const skills = new Map();
      const texts = Object.fromEntries(textFields.map(field => [field, requirementText(job[field])]));
      for (const [field, text] of Object.entries(texts)) {
        for (const match of text.matchAll(matcher)) {
          const label = canonical(match[0]);
          if (label === 'r') {
            const context = text.slice(Math.max(0, match.index - 45), match.index + 46);
            if (match[0] !== 'R' || !/\b(?:python|sql|sas|statistics|statistical|programming|proficiency|familiarity|language|rstudio)\b/i.test(context) && !field.endsWith('_skills')) continue;
          }
          if (!skills.has(label)) skills.set(label, {label, phrase: match[0], field, category: categories.get(label) ?? '', links: links.get(label) ?? []});
        }
      }
      return {
        title: titleGrouping(job.job_title, reference.titleAliases, titleRules),
        family: !isMissing(job.job_family) && !/^(?:other|unclassified|general)$/i.test(plain(job.job_family)) ? normalize(job.job_family) : '',
        location: locationGrouping(job.location, reference.regions, reference.cities),
        education: educationLevel(job, educationRules), experience: experienceDurations(job, texts),
        month: postingMonth(job.posting_date), skills: [...skills.values()],
      };
    },
  };
}
