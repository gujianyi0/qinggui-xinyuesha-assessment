export const shared={snapshot:null,owner:false,busy:false,error:null,readonly:true};
export async function initShared(){}
export async function refreshShared(){}
export async function loginOwner(){throw Error('本地检阅副本不管理云端进度')}
export async function logoutOwner(){}
export async function setMastery(){throw Error('本地检阅副本只读')}
