// Realistic demo book so a first-time visitor sees value before typing anything.
const day = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

const SAMPLE_CSV = `Customer Name,Invoice No,Amount,Due Date,Email,Phone
Acme Traders Pvt Ltd,INV-2041,425000,${day(128)},accounts@acmetraders.example,+919812345678
Bluepeak Logistics,INV-2044,186500,${day(74)},finance@bluepeak.example,+919845001122
Corex Interiors,INV-2050,92000,${day(51)},ops@corex.example,
Dunham & Rao LLP,INV-2053,148000,${day(38)},billing@dunhamrao.example,+919900112233
Everline Foods,INV-2061,64500,${day(22)},ap@everline.example,
Fairmount Realty,INV-2066,310000,${day(12)},accounts@fairmount.example,+919700445566
Greenstone Media,INV-2071,28750,${day(4)},hello@greenstone.example,
Harbour Tech,INV-2078,97000,${day(-9)},pay@harbourtech.example,+919600778899`;

export default SAMPLE_CSV;
