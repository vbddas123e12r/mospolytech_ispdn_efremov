$(document).ready(() => {
    $("input[id^='student_']").change((event) => {
        if (event.target.checked == true) {
            $('#hashForm').append(`
                <input type="hidden" name=${event.target.name} value="${event.target.value}">
            `)
        }
        else {
            $(`#hashForm input[name='${event.target.name}']`).remove()
        }
    })
});
