/* Minimal XLSX export: UTF-8 OOXML in a ZIP container, no remote services. */
(()=>{
const enc=new TextEncoder();
const xml=v=>String(v??'').replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]/g,'').slice(0,32767).replace(/[\uD800-\uDBFF]$/,'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const column=i=>{let s='';for(i++;i;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s};
const crcTable=Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0});
const crc=bytes=>{let n=0xffffffff;for(const b of bytes)n=crcTable[(n^b)&255]^(n>>>8);return (n^0xffffffff)>>>0};
function zip(files){
 const local=[],central=[];let offset=0,size=0;
 const header=(n,values)=>{const b=new Uint8Array(n),v=new DataView(b.buffer);for(const [at,value,width] of values)width===2?v.setUint16(at,value,true):v.setUint32(at,value,true);return b};
 for(const [name,text] of Object.entries(files)){
  const fn=enc.encode(name),bytes=enc.encode(text),checksum=crc(bytes);
  const h=header(30,[[0,0x04034b50,4],[4,20,2],[6,0x800,2],[12,33,2],[14,checksum,4],[18,bytes.length,4],[22,bytes.length,4],[26,fn.length,2]]);
  const c=header(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[8,0x800,2],[14,33,2],[16,checksum,4],[20,bytes.length,4],[24,bytes.length,4],[28,fn.length,2],[42,offset,4]]);
  local.push(h,fn,bytes);central.push(c,fn);offset+=h.length+fn.length+bytes.length;size+=c.length+fn.length;
 }
 const end=header(22,[[0,0x06054b50,4],[8,Object.keys(files).length,2],[10,Object.keys(files).length,2],[12,size,4],[16,offset,4]]);
 return new Blob([...local,...central,end],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
window.makeExcelWorkbook=(titles,rows)=>{
 if(!titles.length||rows.length>1048575)throw Error('Слишком много строк для одного листа Excel');
 const widths=titles.map((_,i)=>[32,22,26,48,27,34,24,30,38,32,22,22,30,22,55][i]||28);
 const data=[titles,...rows].map((row,i)=>`<row r="${i+1}"${i===0?' ht="32" customHeight="1"':''}>${titles.map((_,j)=>`<c r="${column(j)}${i+1}" t="inlineStr" s="${i===0?1:0}"><is><t xml:space="preserve">${xml(row[j])}</t></is></c>`).join('')}</row>`).join('');
 const ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
 const files={
 '[Content_Types].xml':'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
 '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
 'xl/workbook.xml':`<workbook xmlns="${ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Компании" sheetId="1" r:id="rId1"/></sheets></workbook>`,
 'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
 'xl/styles.xml':`<styleSheet xmlns="${ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1959A6"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1" applyNumberFormat="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`,
 'xl/worksheets/sheet1.xml':`<worksheet xmlns="${ns}"><dimension ref="A1:${column(titles.length-1)}${rows.length+1}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="30"/><cols>${widths.map((w,i)=>`<col min="${i+1}" max="${i+1}" width="${w}" customWidth="1"/>`).join('')}</cols><sheetData>${data}</sheetData><autoFilter ref="A1:${column(titles.length-1)}${rows.length+1}"/></worksheet>`
 };
 return zip(files);
};
window.downloadExcel=(titles,rows)=>{
 const url=URL.createObjectURL(window.makeExcelWorkbook(titles,rows)),a=document.createElement('a');a.href=url;a.download='Компании-'+new Date().toISOString().slice(0,10)+'.xlsx';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
})();
