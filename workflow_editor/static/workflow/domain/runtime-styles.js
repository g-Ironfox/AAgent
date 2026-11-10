const classNames = new Map();
const runtimeRules = new Map();
let nextClassId = 0;
let workflowStyleSheet = null;

function stylesheet() {
  if (workflowStyleSheet && [...document.styleSheets].includes(workflowStyleSheet)) {
    return workflowStyleSheet;
  }
  const link = [...document.querySelectorAll('link[href]')].find((item) => item.href.includes('/css/workflow.css'));
  if (workflowStyleSheet !== (link?.sheet || null)) runtimeRules.clear();
  workflowStyleSheet = link?.sheet || null;
  if (!workflowStyleSheet) throw new Error('Workflow stylesheet is not loaded');
  return workflowStyleSheet;
}

export function setRuntimeStyles(element, key, properties) {
  let className = classNames.get(key);
  if (!className) {
    className = `workflow-runtime-${nextClassId++}`;
    classNames.set(key, className);
  }
  element.classList.add(className);

  const sheet = stylesheet();
  let rule = runtimeRules.get(className);
  if (!rule) {
    const index = sheet.insertRule(`.${className}.${className} {}`, sheet.cssRules.length);
    rule = sheet.cssRules[index];
    runtimeRules.set(className, rule);
  }
  rule.style.cssText = '';
  for (const [property, value] of Object.entries(properties)) {
    rule.style.setProperty(property, String(value));
  }
}
