// Example bills so someone can see the whole thing work before typing anything.
const day = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

const SAMPLE_ROWS = [
  { customer: "Acme Traders Pvt Ltd", invoice_no: "INV-2041", amount: 425000, due_date: day(128), email: "accounts@acmetraders.example", phone: "+919812345678", confidence: "high" },
  { customer: "Bluepeak Logistics", invoice_no: "INV-2044", amount: 186500, due_date: day(74), email: "finance@bluepeak.example", phone: "+919845001122", confidence: "high" },
  { customer: "Corex Interiors", invoice_no: "INV-2050", amount: 92000, due_date: day(51), email: "ops@corex.example", phone: "", confidence: "high" },
  { customer: "Dunham & Rao LLP", invoice_no: "INV-2053", amount: 148000, due_date: day(38), email: "billing@dunhamrao.example", phone: "+919900112233", confidence: "high" },
  { customer: "Everline Foods", invoice_no: "INV-2061", amount: 64500, due_date: day(22), email: "ap@everline.example", phone: "", confidence: "high" },
  { customer: "Fairmount Realty", invoice_no: "INV-2066", amount: 310000, due_date: day(12), email: "accounts@fairmount.example", phone: "+919700445566", confidence: "high" },
  { customer: "Greenstone Media", invoice_no: "INV-2071", amount: 28750, due_date: day(4), email: "hello@greenstone.example", phone: "", confidence: "high" },
  { customer: "Harbour Tech", invoice_no: "INV-2078", amount: 97000, due_date: day(-9), email: "pay@harbourtech.example", phone: "+919600778899", confidence: "high" },
];

export default SAMPLE_ROWS;
