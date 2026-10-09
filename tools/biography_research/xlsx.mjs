// Local-only XLSX authoring using the bundled artifact-tool runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const library=process.env.ARTIFACT_TOOL_MODULE;
const {Workbook,SpreadsheetFile}=await import(library?pathToFileURL(library).href:'@oai/artifact-tool');
const [selectionPath,outputPath,progressPath]=process.argv.slice(2);
if(!selectionPath||!outputPath) throw new Error('Usage: xlsx.mjs selection.json output.xlsx [progress.json]');
const selection=JSON.parse(await fs.readFile(selectionPath,'utf8'));
const progress=progressPath?JSON.parse(await fs.readFile(progressPath,'utf8')):{};
const headers=Object.keys(selection.rows[0]);
const extra=['Биография (черновик)','Источники URL/документы','Статус исследования','Основание идентификации','Факты и evidence','Причина/примечание'];
const cols=progressPath?[...headers,...extra]:headers;
const rows=selection.rows.map(row=>{
  const values=headers.map(k=>row[k]??'');
  if(!progressPath)return values;
  const r=progress[row.person_id]??{};
  return [...values,r.biography??'',(r.source_urls??[]).join('\n'),r.status??'Не исследовано',JSON.stringify(r.identity??[]),JSON.stringify(r.evidence??[]),r.notes??''];
});
const wb=Workbook.create();const s=wb.worksheets.add('Кавалеры');
const range=s.getRangeByIndexes(0,0,rows.length+1,cols.length);
range.values=[cols,...rows];
range.format.font={name:'Arial',size:10};
range.format.rowHeight=52;
range.format.wrapText=true;
range.format.columnWidth=23;
s.getRangeByIndexes(0,0,1,cols.length).format={fill:'#24364B',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:56,wrapText:true};
s.getRange('A:A').format.columnWidth=10;s.getRange('B:B').format.columnWidth=14;
s.getRange('C:C').format.columnWidth=36;s.getRange('E:E').format.columnWidth=24;
s.getRange('I:I').format.columnWidth=60;
s.getRange('J:J').format.columnWidth=46;s.getRange('L:L').format.columnWidth=34;
if(progressPath){s.getRange('M:M').format.columnWidth=68;s.getRange('N:N').format.columnWidth=52;s.getRange('P:R').format.columnWidth=64;}
s.getRangeByIndexes(1,0,rows.length,cols.length).format.autofitRows();
s.freezePanes.freezeRows(1);s.freezePanes.freezeColumns(3);
wb.recalculate();
const retained=s.getRangeByIndexes(1,0,rows.length,headers.length).values;
if(JSON.stringify(retained)!==JSON.stringify(selection.rows.map(r=>headers.map(k=>r[k]??''))))throw new Error('Original fields changed');
await fs.mkdir(path.dirname(outputPath),{recursive:true,mode:0o700});
try{await fs.stat(outputPath);throw new Error('Refusing to overwrite existing workbook');}catch(e){if(e.code!=='ENOENT')throw e;}
const blob=await SpreadsheetFile.exportXlsx(wb);await blob.save(outputPath);
await fs.chmod(outputPath,0o600);
const preview=await wb.render({sheetName:s.name,range:progressPath?'M1:O3':'A1:F4',scale:1,format:'png'});
await fs.writeFile(outputPath+'.preview.png',new Uint8Array(await preview.arrayBuffer()),{mode:0o600});
console.log(JSON.stringify({rows:rows.length,originalColumns:headers.length,outputColumns:cols.length,originalFieldsPreserved:true}));
